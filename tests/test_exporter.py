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

"""The Elmer case: its .sif against the mesh groups, and a run where Elmer is installed."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Dict, List

import pytest

from klayout_pex import pex25d


def export(scene, tmp_path: Path, prefix: str = '', **options):
    written = pex25d.export(scene, 'elmer', str(tmp_path), prefix=prefix, options=options)
    return written, Path(written[0]).read_text(), json.loads(Path(written[2]).read_text())


def sections(sif: str) -> Dict[str, List[str]]:
    """{'Body 1': ['Name = "fox"', ...], ...}"""
    return {match.group(1): [line.strip() for line in match.group(2).strip().splitlines()]
            for match in re.finditer(r'^(\w[\w ]*?)\n(.*?)^End$', sif, re.M | re.S)}


def test_registered_as_exporter_plugin():
    info = pex25d.exporter_registry().get_info('elmer')
    assert info.distribution == 'klayout-pex-plugin-elmer'
    assert info.target == 'klayout_pex_plugins.elmer:create_exporter'


def test_sif_matches_the_mesh_groups(two_nets, tmp_path: Path):
    written, sif, groups = export(two_nets, tmp_path)
    assert written == [str(tmp_path / name) for name in ('case.sif', 'mesh.msh', 'mesh.json')]
    blocks = sections(sif)

    assert blocks['Header'] == ['Mesh DB "." "mesh"']
    assert 'Coordinate Scaling = Real 1e-06' in blocks['Simulation']
    assert 'Calculate Capacitance Matrix = True' in blocks['Solver 1']
    for group in groups['dielectrics']:
        tag = group['tag']
        assert f'Target Bodies(1) = {tag}' in blocks[f'Body {tag}']
        assert f'Relative Permittivity = Real {group["permittivity"]}' \
            in blocks[f'Material {tag}']
    for group in groups['terminals']:
        tag = group['tag']
        assert blocks[f'Boundary Condition {tag}'] == [
            f'Name = "{group["name"]}"', f'Target Boundaries(1) = {tag}',
            f'Capacitance Body = {tag}']
    outer = groups['outer_boundary']['tag']
    assert blocks[f'Boundary Condition {outer}'] == [
        'Name = "outer_boundary"', f'Target Boundaries(1) = {outer}']


def test_ground_outer_boundary(two_nets, tmp_path: Path):
    _, sif, groups = export(two_nets, tmp_path, outer_boundary='ground')
    outer = groups['outer_boundary']['tag']
    assert sections(sif)[f'Boundary Condition {outer}'][-1] == 'Capacitance Body = 0'


def test_prefix_names_the_mesh_directory(two_nets, tmp_path: Path):
    written, sif, _ = export(two_nets, tmp_path, prefix='tiny_')
    assert [Path(path).name for path in written] == ['tiny_case.sif', 'tiny_mesh.msh',
                                                     'tiny_mesh.json']
    assert sections(sif)['Header'] == ['Mesh DB "." "tiny_mesh"']


@pytest.mark.parametrize('options, message', [
    ({'outer_boundary': 'open'}, "'outer_boundary' must be one of zero_charge, ground"),
    ({'linear_tol': '1e-10'}, "'linear_tol' must be float"),
    ({'order': 2}, "unexpected keyword argument 'order'"),
], ids=['boundary', 'type', 'unknown'])
def test_invalid_options_are_export_errors(two_nets, tmp_path: Path, options, message: str):
    with pytest.raises(pex25d.ExportError, match=message):
        pex25d.export(two_nets, 'elmer', str(tmp_path), options=options)


@pytest.mark.skipif(shutil.which('ElmerSolver') is None or shutil.which('ElmerGrid') is None,
                    reason="Elmer is not installed")
def test_elmer_solves_the_case(two_nets, tmp_path: Path):
    export(two_nets, tmp_path)
    for command in (['ElmerGrid', '14', '2', 'mesh.msh', '-autoclean'],
                    ['ElmerSolver', 'case.sif']):
        subprocess.run(command, cwd=tmp_path, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    rows = [[float(value) for value in line.split()]
            for line in (tmp_path / 'cmatrix.dat').read_text().splitlines() if line.strip()]
    assert len(rows) == 4 and all(len(row) == 4 for row in rows)
    for i in range(4):
        for j in range(4):
            assert rows[i][j] == pytest.approx(rows[j][i], rel=1e-6)
            if i != j:
                assert rows[i][j] > 0      # mutual capacitances: every pair couples
