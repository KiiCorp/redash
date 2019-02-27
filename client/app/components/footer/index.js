import template from './footer.html';

function controller(clientConfig, currentUser) {
  this.version = clientConfig.version;
  this.varanus_redash_version = clientConfig.varanus_redash_version;
  this.newVersionAvailable = clientConfig.newVersionAvailable && currentUser.isAdmin;
}

export default function init(ngModule) {
  ngModule.component('footer', {
    template,
    controller,
  });
}
