{
  description = "Agentix — safety-first control layer for NixOS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
      pkgsFor = system: nixpkgs.legacyPackages.${system};
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = pkgsFor system;
          agentix = pkgs.python3Packages.buildPythonApplication {
            pname = "agentix";
            version = "0.3.0";
            src = ./.;
            format = "pyproject";

            build-system = [ pkgs.python3Packages.hatchling ];

            nativeCheckInputs = [ pkgs.python3Packages.pytest ];
            checkPhase = ''
              runHook preCheck
              pytest tests/ -x
              runHook postCheck
            '';

            meta = {
              description = "Safety-first control layer for NixOS";
              homepage = "https://github.com/Beach-Bum/Agentix";
              license = pkgs.lib.licenses.mit;
              mainProgram = "agentix";
            };
          };
        in
        {
          default = agentix;
          agentix = agentix;
        }
      );

      devShells = forAllSystems (system:
        let
          pkgs = pkgsFor system;
        in
        {
          default = pkgs.mkShell {
            packages = [
              (pkgs.python3.withPackages (ps: [ ps.pytest ]))
              pkgs.ruff
              pkgs.git
            ];
            shellHook = ''
              echo "agentix dev shell — python $(python3 --version | cut -d' ' -f2), git $(git --version | cut -d' ' -f3)"
            '';
          };
        }
      );
    };
}
