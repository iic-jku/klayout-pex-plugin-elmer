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
