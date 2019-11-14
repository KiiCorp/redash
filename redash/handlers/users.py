import re
import time
from flask import make_response, request, Response
from flask_restful import abort
from flask_login import current_user, login_user
from funcy import project
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError
from disposable_email_domains import blacklist
from funcy import partial

from redash import models, limiter
from redash.permissions import require_permission, require_admin_or_owner, is_admin_or_owner, \
    require_permission_or_owner, require_admin
from redash.handlers.base import BaseResource, require_fields, get_object_or_404, paginate, order_results as _order_results

from redash.authentication.account import invite_link_for_user, send_invite_email, send_password_reset_email, send_verify_email
from redash.settings import parse_boolean
from redash import settings

from redash.handlers.base import NoCheckResource

# Ordering map for relationships
order_map = {
    'name': 'name',
    '-name': '-name',
    'active_at': 'active_at',
    '-active_at': '-active_at',
    'created_at': 'created_at',
    '-created_at': '-created_at',
    'groups': 'group_ids',
    '-groups': '-group_ids',
}

order_results = partial(
    _order_results,
    default_order='-created_at',
    allowed_orders=order_map,
)


def invite_user(org, inviter, user, send_email=True):
    d = user.to_dict()

    invite_url = invite_link_for_user(user)
    if settings.email_server_is_configured() and send_email:
        send_invite_email(inviter, user, invite_url, org)
    else:
        d['invite_link'] = invite_url

    return d


class UserListResource(BaseResource):
    decorators = BaseResource.decorators + \
        [limiter.limit('200/day;50/hour', methods=['POST'])]

    def get_users(self, disabled, pending, search_term):
        if disabled:
            users = models.User.all_disabled(self.current_org)
        else:
            users = models.User.all(self.current_org)

        if pending is not None:
            users = models.User.pending(users, pending)

        if search_term:
            users = models.User.search(users, search_term)
            self.record_event({
                'action': 'search',
                'object_type': 'user',
                'term': search_term,
                'pending': pending,
            })
        else:
            self.record_event({
                'action': 'list',
                'object_type': 'user',
                'pending': pending,
            })

        # order results according to passed order parameter,
        # special-casing search queries where the database
        # provides an order by search rank
        return order_results(users, fallback=not bool(search_term))

    @require_permission('list_users')
    def get(self):
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 25, type=int)

        groups = {group.id: group for group in models.Group.all(self.current_org)}

        def serialize_user(user):
            d = user.to_dict()
            user_groups = []
            for group_id in set(d['groups']):
                group = groups.get(group_id)

                if group:
                    user_groups.append({'id': group.id, 'name': group.name})

            d['groups'] = user_groups

            return d

        search_term = request.args.get('q', '')

        disabled = request.args.get('disabled', 'false')  # get enabled users by default
        disabled = parse_boolean(disabled)

        pending = request.args.get('pending', None)  # get both active and pending by default
        if pending is not None:
            pending = parse_boolean(pending)

        users = self.get_users(disabled, pending, search_term)

        return paginate(users, page, page_size, serialize_user)

    @require_admin
    def post(self):
        req = request.get_json(force=True)
        require_fields(req, ('name', 'email'))

        if '@' not in req['email']:
            abort(400, message='Bad email address.')
        name, domain = req['email'].split('@', 1)

        if domain.lower() in blacklist or domain.lower() == 'qq.com':
            abort(400, message='Bad email address.')

        user = models.User(org=self.current_org,
                           name=req['name'],
                           email=req['email'],
                           is_invitation_pending=True,
                           group_ids=[self.current_org.default_group.id])

        try:
            models.db.session.add(user)
            models.db.session.commit()
        except IntegrityError as e:
            if "email" in e.message:
                abort(400, message='Email already taken.')
            abort(500)

        self.record_event({
            'action': 'create',
            'object_id': user.id,
            'object_type': 'user'
        })

        should_send_invitation = 'no_invite' not in request.args
        return invite_user(self.current_org, self.current_user, user, send_email=should_send_invitation)

class UserCreateResource(BaseResource):
    @require_admin
    def post(self):
        req = request.get_json(force=True)
        require_fields(req, ('name', 'email', 'password'))

        user = models.User(org=self.current_org,
                           name=req['name'],
                           email=req['email'],
                           group_ids=[self.current_org.default_group.id])
        user.hash_password(req['password'])

        try:
            models.db.session.add(user)
            models.db.session.commit()
        except IntegrityError as e:
            if "email" in e.message:
                abort(400, message='Email already taken.')

            abort(500)

        self.record_event({
            'action': 'create',
            'timestamp': int(time.time()),
            'object_id': user.id,
            'object_type': 'user'
        })

        d = user.to_dict(with_api_key=True)

        return d

class UserInviteResource(BaseResource):
    @require_admin
    def post(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        return invite_user(self.current_org, self.current_user, user)


class UserResetPasswordResource(BaseResource):
    @require_admin
    def post(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        if user.is_disabled:
            abort(404, message='Not found')
        reset_link = send_password_reset_email(user)

        return {
            'reset_link': reset_link,
        }


class UserRegenerateApiKeyResource(BaseResource):
    def post(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        if user.is_disabled:
            abort(404, message='Not found')
        if not is_admin_or_owner(user_id):
            abort(403)

        user.regenerate_api_key()
        models.db.session.commit()

        self.record_event({
            'action': 'regnerate_api_key',
            'object_id': user.id,
            'object_type': 'user'
        })

        return user.to_dict(with_api_key=True)


class UserResource(BaseResource):
    decorators = BaseResource.decorators + \
        [limiter.limit('50/hour', methods=['POST'])]

    def get(self, user_id):
        require_permission_or_owner('list_users', user_id)
        user = get_object_or_404(models.User.get_by_id_and_org, user_id, self.current_org)

        self.record_event({
            'action': 'view',
            'object_id': user_id,
            'object_type': 'user',
        })

        return user.to_dict(with_api_key=is_admin_or_owner(user_id))

    def post(self, user_id):
        require_admin_or_owner(user_id)
        user = models.User.get_by_id_and_org(user_id, self.current_org)

        req = request.get_json(True)

        params = project(req, ('email', 'name', 'password', 'old_password', 'group_ids'))

        if 'password' in params and 'old_password' not in params:
            abort(403, message="Must provide current password to update password.")

        if 'old_password' in params and not user.verify_password(params['old_password']):
            abort(403, message="Incorrect current password.")

        if 'password' in params:
            user.hash_password(params.pop('password'))
            params.pop('old_password')

        if 'group_ids' in params:
            if not self.current_user.has_permission('admin'):
                abort(403, message="Must be admin to change groups membership.")

            for group_id in params['group_ids']:
                try:
                    models.Group.get_by_id_and_org(group_id, self.current_org)
                except NoResultFound:
                    abort(400, message="Group id {} is invalid.".format(group_id))

            if len(params['group_ids']) == 0:
                params.pop('group_ids')

        if 'email' in params:
            _, domain = params['email'].split('@', 1)

            if domain.lower() in blacklist or domain.lower() == 'qq.com':
                abort(400, message='Bad email address.')

        email_address_changed = 'email' in params and params['email'] != user.email
        needs_to_verify_email = email_address_changed and settings.email_server_is_configured()
        if needs_to_verify_email:
            user.is_email_verified = False

        try:
            self.update_model(user, params)
            models.db.session.commit()

            if needs_to_verify_email:
                send_verify_email(user, self.current_org)

            # The user has updated their email or password. This should invalidate all _other_ sessions,
            # forcing them to log in again. Since we don't want to force _this_ session to have to go
            # through login again, we call `login_user` in order to update the session with the new identity details.
            if current_user.id == user.id:
                login_user(user, remember=True)
        except IntegrityError as e:
            if "email" in e.message:
                message = "Email already taken."
            else:
                message = "Error updating record"

            abort(400, message=message)

        self.record_event({
            'action': 'edit',
            'object_id': user.id,
            'object_type': 'user',
            'updated_fields': params.keys()
        })

        return user.to_dict(with_api_key=is_admin_or_owner(user_id))

    @require_admin
    def delete(self, user_id):
        extend = request.args.get('extend')
        if extend is None:
            return self.original_delete(user_id)
        else:
            return self.varanus_delete(user_id)

    def original_delete(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        # admin cannot delete self; current user is an admin (`@require_admin`)
        # so just check user id
        if user.id == current_user.id:
            abort(403, message="You cannot delete your own account. "
                               "Please ask another admin to do this for you.")
        elif not user.is_invitation_pending:
            abort(403, message="You cannot delete activated users. "
                               "Please disable the user instead.")
        models.db.session.delete(user)
        models.db.session.commit()

        return user.to_dict(with_api_key=is_admin_or_owner(user_id))

    def varanus_delete(self, user_id):
        # TODO: delete referred tables rows with CASCADE DELETE.
        try:
            def deleteAlerts(alerts):
                id = [alert.id for alert in alerts]
                models.AlertSubscription.query.filter(models.AlertSubscription.alert_id.in_(id)).delete(synchronize_session='fetch')
                alerts.delete(synchronize_session='fetch')

            def deleteQueries(queries):
                id = [query.id for query in queries]
                alerts = models.Alert.query.filter(models.Alert.query_id.in_(id))
                deleteAlerts(alerts)
                visualizations = models.Visualization.query.filter(models.Visualization.query_id.in_(id))
                id = [visualization.id for visualization in visualizations]
                models.Widget.query.filter(models.Widget.visualization_id.in_(id)).delete(synchronize_session='fetch')
                visualizations.delete(synchronize_session='fetch')
                queries.delete()

            models.AccessPermission.query.filter(models.AccessPermission.grantor_id == user_id).delete()
            models.AccessPermission.query.filter(models.AccessPermission.grantee_id == user_id).delete()
            models.AlertSubscription.query.filter(models.AlertSubscription.user_id == user_id).delete()
            models.QuerySnippet.query.filter(models.QuerySnippet.user_id == user_id).delete()
            models.ApiKey.query.filter(models.ApiKey.created_by_id == user_id).delete()
            models.Change.query.filter(models.Change.user_id == user_id).delete()
            models.Event.query.filter(models.Event.user_id == user_id).delete()

            dashboards = models.Dashboard.query.filter(models.Dashboard.user_id == user_id)
            id = [dashboard.id for dashboard in dashboards]
            models.Widget.query.filter(models.Widget.dashboard_id.in_(id)).delete(synchronize_session='fetch')
            dashboards.delete()


            notification_destinations = models.NotificationDestination.query.filter(models.NotificationDestination.user_id == user_id)
            id = [notification_destination.id for notification_destination in notification_destinations]
            models.AlertSubscription.query.filter(models.AlertSubscription.destination_id.in_(id)).delete(synchronize_session='fetch')
            notification_destinations.delete()

            alerts = models.Alert.query.filter(models.Alert.user_id == user_id)
            deleteAlerts(alerts)

            queries = models.Query.query.filter(models.Query.user_id == user_id)
            deleteQueries(queries)

            queries = models.Query.query.filter(models.Query.last_modified_by_id == user_id)
            deleteQueries(queries)

            models.User.query.filter(models.User.id == user_id, models.User.org == self.current_org).delete()
            models.db.session.commit()
        except IntegrityError as e:
            abort(500)

        return Response(status = 204, content_type = "")


class UserForcibleGetResource(NoCheckResource):
    def get(self):
        args = request.args
        user = get_object_or_404(models.User.get_by_email_and_org, args['email'], self.current_org)
        if not user.verify_password(args['password']):
            abort(404)

        return user.to_dict(True)


class UserDisableResource(BaseResource):
    @require_admin
    def post(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        # admin cannot disable self; current user is an admin (`@require_admin`)
        # so just check user id
        if user.id == current_user.id:
            abort(403, message="You cannot disable your own account. "
                               "Please ask another admin to do this for you.")
        user.disable()
        models.db.session.commit()

        return user.to_dict(with_api_key=is_admin_or_owner(user_id))

    @require_admin
    def delete(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        user.enable()
        models.db.session.commit()

        return user.to_dict(with_api_key=is_admin_or_owner(user_id))
