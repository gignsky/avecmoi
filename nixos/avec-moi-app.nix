# avec-moi.app — Ask an Appraiser question box (Python server on :8080),
# packaged as an OCI image by the `avec-moi` flake input. Drop-in replacement
# for .dotfiles/containers/services/avec-moi-app.nix.
#
# The image comes from `avec-moi.packages.<system>.default` (a
# `dockerTools.buildLayeredImage` tarball tagged `avecmoi:latest`). NOTE:
# `packages.<system>.app` is NOT the image — it is the server wrapper the
# image runs. We reference the input by `pkgs.system` so the module does not
# need `system` threaded through `specialArgs`.
#
# Before the first switch, add to nix-secrets/secrets.yaml (`just sops`) a key
# `avec-moi-env` whose value is an env file:
#   ADMIN_PASSWORD=<password for https://<site>/admin>
# validateSopsFiles is on, so the build fails until the key exists.
#
# Submitted questions land in /var/lib/avec-moi/questions.jsonl.
{
  config,
  inputs,
  pkgs,
  ...
}:
let
  imageFile = inputs.avec-moi.packages.${pkgs.system}.default;
in
{
  sops.secrets.avec-moi-env = { };

  systemd.tmpfiles.rules = [ "d /var/lib/avec-moi 0750 root root -" ];

  virtualisation.oci-containers.containers.avec-moi-app = {
    inherit imageFile;
    image = "avecmoi:latest";
    autoStart = true;
    environmentFiles = [ config.sops.secrets.avec-moi-env.path ];
    environment = {
      TZ = "America/New_York";
    };
    volumes = [ "/var/lib/avec-moi:/data" ];
    ports = [
      "8081:8080/tcp"
    ];
  };
  networking.firewall = {
    enable = true;
    allowedTCPPorts = [ 8081 ];
  };
}
