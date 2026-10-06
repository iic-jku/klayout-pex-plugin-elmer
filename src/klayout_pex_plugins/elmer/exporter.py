#
# --------------------------------------------------------------------------------
# SPDX-FileCopyrightText: 2026 Martin Jan Köhler and Harald Pretl
# Johannes Kepler University, Institute for Integrated Circuits.
#
# This file is part of klayout-pex-plugin-elmer
# (see https://github.com/iic-jku/klayout-pex-plugin-elmer).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# SPDX-License-Identifier: GPL-3.0-or-later
# --------------------------------------------------------------------------------
#

"""
The exporter ``elmer``: an Elmer FEM electrostatics case (StatElecSolver) whose
result is the Maxwell capacitance matrix of every net, floating conductor and the
ground plane.

Elmer reads its own mesh format, so the gmsh mesh is converted first; both steps
run in the output directory::

    ElmerGrid 14 2 mesh.msh -autoclean
    ElmerSolver case.sif

ElmerSolver writes the matrix to ``cmatrix.dat``; capacitance body *i* there is
the group with tag *i* in ``mesh.json``.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import TYPE_CHECKING, Any, ClassVar, List, Mapping, Optional

from klayout_pex.log import info
from klayout_pex.plugin_api.v1 import PEX25DSceneExporter
from klayout_pex_plugins.gmsh import (LENGTH_UNIT_M, GmshMeshOptions, MeshResult,
                                      parse_options, write_mesh)

if TYPE_CHECKING:
    from klayout_pex_protobuf.kpex.pex25d.pex25d_scene_pb2 import PEX25DScene

OUTER_BOUNDARY_CONDITIONS = ('zero_charge', 'ground')

VACUUM_PERMITTIVITY = 8.8541878128e-12
"""F/m, CODATA 2018."""


@dataclass
class ElmerExporterOptions(GmshMeshOptions):
    """The mesh's settings, and Elmer's."""

    outer_boundary: str = 'zero_charge'
    """
    The domain box: ``zero_charge`` (no field crosses it, Elmer's natural boundary
    condition) or ``ground`` (0 V). Each biases the matrix the other way; a larger
    field margin shrinks both effects.
    """

    linear_tol: float = 1.0e-10
    """Relative residual of the linear solver."""

    linear_max_iterations: int = 1000

    def __post_init__(self):
        super().__post_init__()
        if self.outer_boundary not in OUTER_BOUNDARY_CONDITIONS:
            raise ValueError(f"'outer_boundary' must be one of "
                             f"{', '.join(OUTER_BOUNDARY_CONDITIONS)}")


class ElmerSceneExporter(PEX25DSceneExporter):
    """Write an Elmer FEM electrostatics case from a resolved PEX25D scene."""

    name: ClassVar[str] = 'elmer'
    default_prefix: ClassVar[str] = ''

    def export(self,
               scene: PEX25DScene,
               *,
               output_dir_path: str,
               prefix: str = '',
               options: Optional[Mapping[str, Any]] = None) -> List[str]:
        """Return the case first, then the mesh and the JSON naming its groups."""
        settings = parse_options(ElmerExporterOptions, options, self.name)
        prefix = prefix or self.default_prefix
        mesh = write_mesh(scene, settings, output_dir_path, prefix)

        sif_path = os.path.join(output_dir_path, f"{prefix}case.sif")
        with open(sif_path, 'w', encoding='utf-8') as file:
            file.write(elmer_sif(mesh, settings))
        info(f"Run Elmer in {output_dir_path}: "
             f"ElmerGrid 14 2 {os.path.basename(mesh.msh_path)} -autoclean && "
             f"ElmerSolver {os.path.basename(sif_path)}")
        return [sif_path, *mesh.paths]


def elmer_sif(mesh: MeshResult, settings: ElmerExporterOptions) -> str:
    """The solver input file; ElmerGrid names the mesh directory after the .msh file."""
    mesh_dir = os.path.splitext(os.path.basename(mesh.msh_path))[0]
    lines = [
        '! Electrostatics of a PEX25D scene, written by klayout-pex-plugin-elmer.',
        f'! Capacitance body i is the terminal with tag i in {mesh_dir}.json.',
        '',
        'Header',
        f'  Mesh DB "." "{mesh_dir}"',
        'End',
        '',
        'Simulation',
        '  Max Output Level = 5',
        '  Coordinate System = Cartesian 3D',
        f'  Coordinate Scaling = Real {LENGTH_UNIT_M}',
        '  Simulation Type = Steady State',
        '  Steady State Max Iterations = 1',
        'End',
        '',
        'Constants',
        f'  Permittivity Of Vacuum = Real {VACUUM_PERMITTIVITY}',
        'End',
        '',
        'Equation 1',
        '  Active Solvers(1) = 1',
        'End',
        '',
        'Solver 1',
        '  Equation = Stat Elec Solver',
        '  Procedure = "StatElecSolve" "StatElecSolver"',
        '  Variable = Potential',
        '  Variable DOFs = 1',
        '  Calculate Electric Field = False',
        '  Calculate Electric Flux = False',
        '  Calculate Capacitance Matrix = True',
        '  Capacitance Matrix Filename = File "cmatrix.dat"',
        '  Linear System Solver = Iterative',
        '  Linear System Iterative Method = BiCGStabl',
        '  Linear System Preconditioning = ILU1',
        f'  Linear System Max Iterations = {settings.linear_max_iterations}',
        f'  Linear System Convergence Tolerance = {settings.linear_tol}',
        '  Linear System Abort Not Converged = True',
        '  Steady State Convergence Tolerance = 1.0e-5',
        'End',
    ]
    for group in mesh.dielectrics:
        lines += [
            '',
            f'Body {group.tag}',
            f'  Name = "{group.name}"',
            f'  Target Bodies(1) = {group.tag}',
            '  Equation = 1',
            f'  Material = {group.tag}',
            'End',
            '',
            f'Material {group.tag}',
            f'  Name = "{group.name}"',
            f'  Relative Permittivity = Real {group.permittivity}',
            'End',
        ]
    for group in mesh.terminals:
        lines += [
            '',
            f'Boundary Condition {group.tag}',
            f'  Name = "{group.name}"',
            f'  Target Boundaries(1) = {group.tag}',
            f'  Capacitance Body = {group.tag}',
            'End',
        ]
    if mesh.outer_boundary is not None:
        group = mesh.outer_boundary
        lines += [
            '',
            f'Boundary Condition {group.tag}',
            f'  Name = "{group.name}"',
            f'  Target Boundaries(1) = {group.tag}',
        ]
        if settings.outer_boundary == 'ground':
            lines.append('  Capacitance Body = 0')
        lines.append('End')
    return '\n'.join(lines) + '\n'
