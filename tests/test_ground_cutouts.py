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

"""Typed mesh capabilities and independent reference geometry for ground openings."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, List
from unittest.mock import patch

import pytest

from klayout_pex import pex25d
from klayout_pex.plugin_api.v1 import SceneCapability
from klayout_pex_plugins.gmsh import GmshSceneExporter
from klayout_pex_plugins.elmer.exporter import ElmerSceneExporter
from .conftest import DATA


def scene(floating: bool = False, reference: bool = False) -> Any:
    text = (DATA/'ground_cutout.pex25d').read_text(encoding='utf-8')
    if floating:
        text = text.replace('CONDUCTOR pin signal', 'CONDUCTOR VSS FLOATING')
        text = text.replace('CONDUCTOR pin LAYER', 'CONDUCTOR VSS LAYER')
    result = pex25d.resolve(pex25d.read_text(text.encode('utf-8')))
    if reference:
        # The resolved-scene contract permits no ground plane. Independently
        # describe its finite reference frame as a metal polygon with a hole.
        # The text format itself still requires a GROUND_PLANE declaration.
        result.ClearField('ground_plane')
        layer = result.layers.add(name='bulk', zlow=-400, zhigh=0)
        layer.kind = layer.RESOLVED_LAYER_KIND_METAL
        frame = type(result.conductors[0])(name='reference', net='VSS')
        polygon = frame.regions.add(layer='bulk').polygons.add()
        for x, y in [(-3000, -3000), (3000, -3000), (3000, 3000), (-3000, 3000)]:
            polygon.outer.points.add(x=x, y=y)
        hole = polygon.holes.add()
        for x, y in [(-1000, -1000), (-1000, 2000), (2000, 2000), (2000, -1000)]:
            hole.points.add(x=x, y=y)
        result.conductors.insert(0, frame)
    return result


def export(scene: Any, directory: Path) -> List[str]:
    return pex25d.export_with_backend(ElmerSceneExporter(), scene, 'elmer', str(directory),
                                      options={'mesh_size_edge_um': .2, 'mesh_size_max_um': 2.0,
                                               'linear_tol': 1e-12})


@pytest.mark.parametrize('capabilities', [None, Ellipsis, frozenset(),
    frozenset({'ground-cutouts', 'electrical-identity'}), frozenset({SceneCapability.GROUND_CUTOUTS}),
    set(SceneCapability), frozenset({SceneCapability.GROUND_CUTOUTS, 'electrical-identity'})])
@pytest.mark.parametrize('direct', [False, True])
def test_old_or_incomplete_mesh_backend_rejects_new_semantics_before_output(
        tmp_path: Path, capabilities: Any, direct: bool):
    with patch.object(GmshSceneExporter, 'supported_capabilities', return_value=capabilities), patch(
            'klayout_pex_plugins.elmer.exporter.write_mesh') as mesh:
        with pytest.raises(pex25d.ExportError, match='does not support required scene capabilities'):
            if direct:
                ElmerSceneExporter().export(scene(), output_dir_path=str(tmp_path/'output'))
            else:
                export(scene(), tmp_path/'output')
        mesh.assert_not_called()
    assert not (tmp_path/'output').exists()


@pytest.mark.parametrize('floating', [False, True])
def test_deck_preserves_reference_and_floating_identity(tmp_path: Path, floating: bool):
    original = scene(floating)
    before = original.SerializeToString(deterministic=True)
    paths = export(original, tmp_path)
    groups = json.loads(Path(paths[2]).read_text(encoding='utf-8'))
    assert [group['name'] for group in groups['terminals']] == [
        'VSS', 'FLOATING:VSS' if floating else 'signal']
    from .test_exporter import sections
    blocks = sections(Path(paths[0]).read_text(encoding='utf-8'))
    for group in groups['terminals']:
        block = blocks[f"Boundary Condition {group['tag']}"]
        assert f'Name = "{group["name"]}"' in block
        assert f"Capacitance Body = {group['tag']}" in block
    if floating:
        assert paths[3:] == [str(tmp_path/'body_names.json')]
        body_map = json.loads(Path(paths[3]).read_text(encoding='utf-8'))
        assert body_map['ground_net'] == 'VSS'
        assert {'kind': 'floating-body', 'name': 'VSS', 'solver_name': 'FLOATING:VSS'} in body_map['bodies']
    else:
        assert len(paths) == 3
    assert original.SerializeToString(deterministic=True) == before


def test_reference_contact_remains_one_electrical_terminal(tmp_path: Path):
    original = scene()
    original.ground_plane.ClearField('cutouts')
    original.conductors[0].net = 'VSS'
    paths = export(original, tmp_path)
    groups = json.loads(Path(paths[2]).read_text(encoding='utf-8'))
    assert [group['name'] for group in groups['terminals']] == ['VSS']


def solve(directory: Path) -> List[List[float]]:
    for command in (['ElmerGrid', '14', '2', 'mesh.msh', '-autoclean'], ['ElmerSolver', 'case.sif']):
        result = subprocess.run(command, cwd=directory, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=120)
        assert result.returncode == 0, result.stdout+result.stderr
    return [[float(value) for value in line.split()]
            for line in (directory/'cmatrix.dat').read_text(encoding='utf-8').splitlines() if line.strip()]


@pytest.mark.skipif(shutil.which('ElmerSolver') is None or shutil.which('ElmerGrid') is None, reason='Elmer is not installed')
@pytest.mark.parametrize('floating', [False, True])
def test_actual_solver_matches_explicit_finite_reference_frame(tmp_path: Path, floating: bool):
    results = []
    for reference in (False, True):
        directory = tmp_path/('reference' if reference else 'cutout')
        export(scene(floating, reference), directory)
        results.append(solve(directory))
    assert all(len(rows) == 2 and all(len(row) == 2 for row in rows) for rows in results)
    for rows in results:
        assert rows[0][1] > 0 and rows[1][0] > 0
        assert rows[0][1] == pytest.approx(rows[1][0], rel=1e-6, abs=0)
        # Elmer's lumped diagonals are coupling to exterior ground. With the
        # zero-charge boundary and both terminals included, they must be zero.
        # Check charge balance to 1e-10 of mutual coupling. The test requests a
        # 1e-12 solver residual because integrated charges accumulate residuals.
        zero_tolerance = rows[0][1] * 1e-10
        assert rows[0][0] == pytest.approx(0, rel=0, abs=zero_tolerance)
        assert rows[1][1] == pytest.approx(0, rel=0, abs=zero_tolerance)
    # The two geometry descriptions represent the same finite body and opening.
    # Keep the physical mutual-capacitance comparison purely relative.
    for i in range(2):
        assert results[0][i][1-i] == pytest.approx(results[1][i][1-i], rel=2e-3, abs=0)


def test_capabilities_are_available_without_constructing_exporter():
    with patch.object(ElmerSceneExporter, '__init__', side_effect=AssertionError('constructed')):
        assert ElmerSceneExporter.supported_capabilities() == frozenset({
            SceneCapability.GROUND_CUTOUTS, SceneCapability.ELECTRICAL_IDENTITY})


@pytest.mark.parametrize('declaration', [None, frozenset(SceneCapability)])
def test_noncallable_mesh_declaration_advertises_no_capabilities(declaration: Any):
    with patch.object(GmshSceneExporter, 'supported_capabilities', declaration):
        assert ElmerSceneExporter.supported_capabilities() == frozenset()


def test_backend_accounting_support_is_not_forwarded():
    with patch.object(GmshSceneExporter, 'supported_capabilities', return_value=frozenset(SceneCapability)):
        assert ElmerSceneExporter.supported_capabilities() == frozenset({
            SceneCapability.GROUND_CUTOUTS, SceneCapability.ELECTRICAL_IDENTITY})


@pytest.mark.parametrize('direct', [False, True])
def test_accounting_is_rejected_before_output(tmp_path: Path, direct: bool):
    from klayout_pex_protobuf.kpex.pex25d.pex25d_capabilities_pb2 import REQUIRED_CAPABILITY_CAPACITANCE_ACCOUNTING
    original = scene()
    original.required_capabilities.append(REQUIRED_CAPABILITY_CAPACITANCE_ACCOUNTING)
    before = original.SerializeToString(deterministic=True)
    directory = tmp_path/'unsupported'
    with pytest.raises(pex25d.ExportError, match='capacitance-accounting'):
        if direct:
            ElmerSceneExporter().export(original, output_dir_path=str(directory))
        else:
            pex25d.export_with_backend(ElmerSceneExporter(), original, 'elmer', str(directory))
    assert not directory.exists()
    assert original.SerializeToString(deterministic=True) == before
