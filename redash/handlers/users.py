import time
from flask import make_response, request, Response
from flask_restful import abort
from funcy import project
from sqlalchemy.exc import IntegrityError

from redash import models
from redash.permissions import require_permission, require_admin_or_owner, is_admin_or_owner, \
    require_permission_or_owner, require_admin
from redash.handlers.base import BaseResource, NoCheckResource, require_fields, get_object_or_404

from redash.authentication.account import invite_link_for_user, send_invite_email, send_password_reset_email


def invite_user(org, inviter, user):
    invite_url = invite_link_for_user(user)
    send_invite_email(inviter, user, invite_url, org)
    return invite_url


class UserListResource(BaseResource):
    @require_permission('list_users')
    def get(self):
        return [u.to_dict() for u in models.User.all(self.current_org)]

    @require_admin
    def post(self):
        req = request.get_json(force=True)
        require_fields(req, ('name', 'email'))

        user = models.User(org=self.current_org,
                           name=req['name'],
                           email=req['email'],
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
            'timestamp': int(time.time()),
            'object_id': user.id,
            'object_type': 'user'
        })

        if request.args.get('no_invite') is not None:
            invite_url = invite_link_for_user(user)
        else:
            invite_url = invite_user(self.current_org, self.current_user, user)

        d = user.to_dict()
        d['invite_link'] = invite_url

        return d

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
        invite_url = invite_user(self.current_org, self.current_user, user)

        d = user.to_dict()
        d['invite_link'] = invite_url

        return d


class UserResetPasswordResource(BaseResource):
    @require_admin
    def post(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        reset_link = send_password_reset_email(user)

        return {
            'reset_link': reset_link,
        }


class UserForcibleGetResource(NoCheckResource):
    def get(self):
        args = request.args
        user = get_object_or_404(models.User.get_by_email_and_org, args['email'], self.current_org)
        if not user.verify_password(args['password']):
            abort(404)

        return user.to_dict(True)


class UserResource(BaseResource):
    def get(self, user_id):
        require_permission_or_owner('list_users', user_id)
        user = get_object_or_404(models.User.get_by_id_and_org, user_id, self.current_org)

        return user.to_dict(with_api_key=is_admin_or_owner(user_id))

    def post(self, user_id):
        require_admin_or_owner(user_id)
        user = models.User.get_by_id_and_org(user_id, self.current_org)

        req = request.get_json(True)

        params = project(req, ('email', 'name', 'password', 'old_password', 'groups'))

        if 'password' in params and 'old_password' not in params:
            abort(403, message="Must provide current password to update password.")

        if 'old_password' in params and not user.verify_password(params['old_password']):
            abort(403, message="Incorrect current password.")

        if 'password' in params:
            user.hash_password(params.pop('password'))
            params.pop('old_password')

        if 'groups' in params and not self.current_user.has_permission('admin'):
            abort(403, message="Must be admin to change groups membership.")

        try:
            self.update_model(user, params)
            models.db.session.commit()
        except IntegrityError as e:
            if "email" in e.message:
                message = "Email already taken."
            else:
                message = "Error updating record"

            abort(400, message=message)

        self.record_event({
            'action': 'edit',
            'timestamp': int(time.time()),
            'object_id': user.id,
            'object_type': 'user',
            'updated_fields': params.keys()
        })

        return user.to_dict(with_api_key=is_admin_or_owner(user_id))

    @require_admin
    def delete(self, user_id):
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
