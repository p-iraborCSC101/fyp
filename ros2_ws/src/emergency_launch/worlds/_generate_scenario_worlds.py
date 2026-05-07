#!/usr/bin/env python3
"""Generate hospital_<scenario>.sdf scenario worlds from the base hospital_world.sdf.

Each scenario adds a different set of <actor> blocks ('humans') with looping
walking trajectories.  Run this whenever the base world or scenario actor lists
change.

Usage:
    python3 _generate_scenario_worlds.py

Outputs alongside this script:
    hospital_low_crowding.sdf
    hospital_moderate_crowding.sdf
    hospital_high_crowding.sdf
"""

from __future__ import annotations

import math
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE / 'hospital_world.sdf'

# --- skin / animation source ---------------------------------------------------
# Gazebo Fuel-hosted standard walking actor.  First Gazebo Sim launch with
# internet caches it; offline runs reuse the cache at ~/.gz/fuel/.
SKIN_URI = (
    'https://fuel.gazebosim.org/1.0/Mingfei/models/actor/tip/files/meshes/walk.dae'
)


def actor_block(name: str, waypoints: list[tuple[float, float, float]], speed: float) -> str:
    """Build an <actor> with a looping walk along the supplied (x, y, time_s) waypoints."""
    wps = []
    cum = 0.0
    prev = waypoints[0]
    wps.append(f'        <waypoint><time>0.000</time>'
               f'<pose>{prev[0]:.2f} {prev[1]:.2f} 1.0 0 0 0</pose></waypoint>')
    for x, y, _ in waypoints[1:]:
        dist = math.hypot(x - prev[0], y - prev[1])
        cum += dist / max(speed, 0.05)
        wps.append(f'        <waypoint><time>{cum:.3f}</time>'
                   f'<pose>{x:.2f} {y:.2f} 1.0 0 0 0</pose></waypoint>')
        prev = (x, y, _)
    return f"""    <actor name='{name}'>
      <pose>{waypoints[0][0]:.2f} {waypoints[0][1]:.2f} 1.0 0 0 0</pose>
      <skin>
        <filename>{SKIN_URI}</filename>
        <scale>1.0</scale>
      </skin>
      <animation name='walk'>
        <filename>{SKIN_URI}</filename>
        <interpolate_x>true</interpolate_x>
      </animation>
      <script>
        <loop>true</loop>
        <delay_start>0</delay_start>
        <auto_start>true</auto_start>
        <trajectory id='0' type='walk'>
{chr(10).join(wps)}
        </trajectory>
      </script>
    </actor>
"""


# Each scenario: list of (name, [waypoints], speed_m_s).
# Waypoints are corridor and door-area loops between y=4.5 and y=7.5 (the
# corridor band) so the humans cross the robot's likely path to the rooms.
SCENARIOS: dict[str, list[tuple[str, list[tuple[float, float, float]], float]]] = {
    'low_crowding': [
        ('human_1', [(2, 5, 0), (14, 5, 0), (2, 5, 0)], 0.4),
        ('human_2', [(13, 7, 0), (5, 7, 0), (13, 7, 0)], 0.4),
    ],
    'moderate_crowding': [
        ('human_1', [(2, 5, 0), (14, 5, 0), (2, 5, 0)], 0.6),
        ('human_2', [(13, 7, 0), (5, 7, 0), (13, 7, 0)], 0.6),
        ('human_3', [(5, 4, 0), (5, 7.5, 0), (5, 4, 0)], 0.6),
        ('human_4', [(11, 4, 0), (11, 7.5, 0), (11, 4, 0)], 0.6),
    ],
    'high_crowding': [
        ('human_1', [(2, 5, 0), (14, 5, 0), (2, 5, 0)], 0.8),
        ('human_2', [(13, 7, 0), (5, 7, 0), (13, 7, 0)], 0.8),
        ('human_3', [(5, 4, 0), (5, 7.5, 0), (5, 4, 0)], 0.8),
        ('human_4', [(11, 4, 0), (11, 7.5, 0), (11, 4, 0)], 0.8),
        ('human_5', [(14, 4, 0), (14, 7.5, 0), (14, 4, 0)], 0.8),
        ('human_6', [(8, 6, 0), (12, 6, 0), (8, 6, 0)], 0.8),
        ('human_7', [(12, 5, 0), (6, 7, 0), (12, 5, 0)], 0.8),
    ],
}


def main() -> None:
    base_xml = BASE.read_text()
    if '</world>' not in base_xml:
        raise SystemExit('Base hospital_world.sdf has no </world> tag')

    for scenario, actors in SCENARIOS.items():
        actor_xml = '\n'.join(actor_block(n, wps, sp) for n, wps, sp in actors)
        world_name_old = "world name='hospital_world'"
        world_name_new = f"world name='hospital_{scenario}'"
        out_xml = base_xml.replace(world_name_old, world_name_new, 1)
        out_xml = out_xml.replace('</world>',
                                  f'\n    <!-- ===== Moving humans (scenario: {scenario}) ===== -->\n'
                                  + actor_xml + '\n  </world>',
                                  1)
        out_path = HERE / f'hospital_{scenario}.sdf'
        out_path.write_text(out_xml)
        print(f'wrote {out_path.relative_to(HERE.parents[3])}  ({len(actors)} actors)')


if __name__ == '__main__':
    main()
