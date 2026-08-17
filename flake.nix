{
  description = "avecmoi.app — slides served by a static web server, packaged as an OCI image";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      # Filenames contain spaces/parens (illegal in store path names), so import
      # them via builtins.path with an explicit sanitized name.
      slides = builtins.path {
        path = ./. + "/Why Appraisers Matter (standalone).html";
        name = "slides.html";
      };
      notes = builtins.path {
        path = ./. + "/Presenter Notes (standalone).html";
        name = "notes.html";
      };

      # The website: slides at /, notes at /notes.html.
      mkSite = pkgs: pkgs.runCommand "avecmoi-site" { } ''
        mkdir -p "$out"
        cp ${slides} "$out/index.html"
        cp ${notes}  "$out/notes.html"
      '';
    in
    {
      # `nix build` -> ./result is a gzipped OCI image tarball.
      #   podman load -i result
      #   podman run -d -p <hostport>:8080 avecmoi:latest
      packages = forAll (pkgs:
        let site = mkSite pkgs;
        in {
          site = site;
          default = pkgs.dockerTools.buildLayeredImage {
            name = "avecmoi";
            tag = "latest";
            config = {
              Cmd = [
                "${pkgs.static-web-server}/bin/static-web-server"
                "--root" site
                "--host" "0.0.0.0"
                "--port" "8080"
              ];
              ExposedPorts = { "8080/tcp" = { }; };
            };
          };
        });

      # `nix run .#serve` -> local preview without building an image.
      apps = forAll (pkgs:
        let site = mkSite pkgs;
        in {
          serve = {
            type = "app";
            program = toString (pkgs.writeShellScript "avecmoi-serve" ''
              set -euo pipefail
              echo "Serving ${site} at http://localhost:8080"
              exec ${pkgs.static-web-server}/bin/static-web-server \
                --root ${site} --host 127.0.0.1 --port 8080
            '');
          };
        });

      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [ pkgs.static-web-server ];
        };
      });
    };
}
