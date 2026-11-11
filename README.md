# klayout-pex-plugin-elmer

[Elmer FEM](https://www.elmerfem.org) electrostatics cases from [KLayout-PEX](https://github.com/iic-jku/klayout-pex) PEX25D scenes: the capacitance matrix of every net, floating conductor and the ground plane, by FEM (StatElecSolver).

## Usage

```bash
pip install klayout-pex-plugin-elmer
pex25d export cell.pex25d --to elmer --out_dir case
cd case && ElmerGrid 14 2 mesh.msh -autoclean && ElmerSolver case.sif
```

- **Output of the exporter:**
  - `case.sif`
  - `mesh.msh` and `mesh.json`, from [klayout-pex-plugin-gmsh](https://github.com/iic-jku/klayout-pex-plugin-gmsh)
- **Running it:** ElmerGrid converts the mesh into the directory `mesh/`, which `case.sif` reads.
- **Result:** `cmatrix.dat`
  - mutual capacitances off the diagonal
  - capacitance to ground on the diagonal, which is zero with the default `outer_boundary`
  - body *i* is the group with tag *i* in `mesh.json`
- **IIC-OSIC-TOOLS doesn't include Elmer.**

## Options

The mesh options of klayout-pex-plugin-gmsh, plus:

| Option | Default | Meaning |
| --- | --- | --- |
| `outer_boundary` | `zero_charge` | Domain box: `zero_charge` (Elmer's natural boundary condition) or `ground` (0 V) |
| `linear_tol` | 1e-10 | Relative residual of the linear solver (BiCGStabl, ILU1) |
| `linear_max_iterations` | 1000 | |

Pass them with `pex25d export --option NAME=VALUE` (klayout-pex 0.6.3 or later) or `options={...}` in Python.

Elements are linear. On the same mesh, the matrix matches Palace with `order` 1.

## Development

```bash
poetry install    # uses ../klayout-pex-plugin-gmsh until it is on PyPI
poetry run pytest # runs ElmerGrid and ElmerSolver too, if they are on PATH
```

## Acknowledgements

This project is funded by the JKU/SAL [IWS Lab](https://research.jku.at/de/projects/jku-lit-sal-intelligent-wireless-systems-lab-iws-lab/), a collaboration of [Johannes Kepler University](https://jku.at) and [Silicon Austria Labs](https://silicon-austria-labs.com).

This project is further funded by the European project [ODE4EC-AMS](https://ode4ec.eu/projects/ams/), which has received funding from the Chips Joint Undertaking (Chips JU) under Grant Agreement No 101252962.

Funded by the European Union. Views and opinions expressed are however those of the author(s) only and do not necessarily reflect those of the European Union or the Chips Joint Undertaking. Neither the European Union nor the granting authority can be held responsible for them.

<p align="center">
  <a href="https://iic.jku.at" target="_blank">
    <img src="https://github.com/iic-jku/klayout-pex-website/raw/main/figures/funding/iic-jku.svg" alt="Johannes Kepler University: Institute for Integrated Circuits and Quantum Computing" width="300"/>
  </a>
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <a href="https://silicon-austria-labs.com" target="_blank">
    <img src="https://github.com/iic-jku/klayout-pex-website/raw/main/figures/funding/silicon-austria-labs-logo.svg" alt="Silicon Austria Labs" width="300"/>
  </a>
</p>

<p align="center">
  <a href="https://ode4ec.eu/projects/ams/" target="_blank">
    <img src="https://github.com/iic-jku/klayout-pex-website/raw/main/figures/funding/eu-cofunded.svg" alt="Co-funded by the European Union" width="300"/>
  </a>
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <a href="https://www.chips-ju.europa.eu" target="_blank">
    <img src="https://github.com/iic-jku/klayout-pex-website/raw/main/figures/funding/chips-ju.png" alt="Chips Joint Undertaking" width="300"/>
  </a>
</p>
