{{flutter_js}}
{{flutter_build_config}}

// SAMCAM sert ce dashboard en local sur la Raspberry Pi, y compris sans
// accès Internet. Par défaut, Flutter charge le moteur de rendu CanvasKit
// depuis le CDN de Google (gstatic.com) même si les fichiers sont déjà
// présents dans build/web/canvaskit/ — ce qui casse le rendu (et donc tout
// l'écran, avec des erreurs type "charCodeAt is not a function") dès que la
// Pi n'a pas Internet. On force ici l'utilisation de la copie locale.
_flutter.loader.load({
  serviceWorkerSettings: {
    serviceWorkerVersion: {{flutter_service_worker_version}}
  },
  config: {
    canvasKitBaseUrl: "canvaskit/"
  }
});
