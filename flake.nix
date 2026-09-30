{
  description = "avecmoi.app — Ask an Appraiser question box (+ archived slides), packaged as an OCI image";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      site = builtins.path { path = ./site; name = "avecmoi-site"; };
      # The previous "Why Appraisers Matter" deck, still served at /matter/.
      archive = builtins.path { path = ./archive/why-appraisers-matter; name = "avecmoi-archive"; };
      server = builtins.path { path = ./server/app.py; name = "avecmoi-app.py"; };

      # Wrapper that runs the question-box server. Questions are appended to
      # $DATA_DIR/questions.jsonl; set ADMIN_PASSWORD to enable /admin.
      mkApp = pkgs: pkgs.writeShellScriptBin "avecmoi" ''
        export SITE_DIR="''${SITE_DIR:-${site}}"
        export ARCHIVE_DIR="''${ARCHIVE_DIR:-${archive}}"
        export DATA_DIR="''${DATA_DIR:-/data}"
        exec ${pkgs.python3}/bin/python3 ${server} "$@"
      '';
    in
    {
      # `nix build` -> ./result is a gzipped OCI image tarball.
      #   podman load -i result
      #   podman run -d --name avecmoi -p <hostport>:8080 \
      #     -v /srv/avecmoi:/data -e ADMIN_PASSWORD=... avecmoi:latest
      packages = forAll (pkgs:
        let app = mkApp pkgs;
        in {
          inherit app;
          default = pkgs.dockerTools.buildLayeredImage {
            name = "avecmoi";
            tag = "latest";
            contents = [ pkgs.dockerTools.caCertificates ];
            extraCommands = "mkdir -p data";
            config = {
              Cmd = [ "${app}/bin/avecmoi" ];
              Env = [ "DATA_DIR=/data" "HOST=0.0.0.0" "PORT=8080" "PYTHONUNBUFFERED=1" ];
              ExposedPorts = { "8080/tcp" = { }; };
              Volumes = { "/data" = { }; };
            };
          };
        });

      # `nix run .#serve` -> local preview; questions go to ./data/.
      apps = forAll (pkgs:
        let app = mkApp pkgs;
        in {
          serve = {
            type = "app";
            program = toString (pkgs.writeShellScript "avecmoi-serve" ''
              set -euo pipefail
              export DATA_DIR="''${DATA_DIR:-$PWD/data}"
              export HOST="''${HOST:-127.0.0.1}"
              echo "Serving at http://$HOST:''${PORT:-8080} (questions -> $DATA_DIR)"
              exec ${app}/bin/avecmoi
            '');
          };
        });

      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [ pkgs.python3 ];
        };
      });
    };
}
