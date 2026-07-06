"""Custom ManiSkill task environments for this harness.

Importing this module registers the environments (via @register_env), so any
entry point that wants them must `import scripts.custom_envs` before calling
gym.make.

ThreeColoredCubes-v1
    A tabletop scene with three same-size cubes (red / green / blue) dropped at
    random, non-overlapping positions each episode. Stage 0 ("the set") for a
    language-conditioned "pick the <color> cube" task — this file defines only
    the scene + seeded randomization; the grasp solution lives elsewhere.
"""
from __future__ import annotations

import sapien
import torch

import mani_skill.envs.utils.randomization as randomization
from mani_skill.envs.tasks.tabletop.pick_cube import PickCubeEnv
from mani_skill.sensors.camera import CameraConfig
from mani_skill.utils import sapien_utils
from mani_skill.utils.building import actors
from mani_skill.utils.registration import register_env
from mani_skill.utils.scene_builder.table import TableSceneBuilder
from mani_skill.utils.structs.pose import Pose

# Visually distinct, same-shape cubes. Order is fixed so an index ↔ color map is
# stable across episodes (useful later for "pick the <color>" instructions).
CUBE_COLORS = [
    ("red", [1.0, 0.1, 0.1, 1.0]),
    ("green", [0.1, 0.85, 0.15, 1.0]),
    ("blue", [0.15, 0.35, 1.0, 1.0]),
]


@register_env("ThreeColoredCubes-v1", max_episode_steps=50)
class ThreeColoredCubesEnv(PickCubeEnv):
    """Three colored cubes randomly placed on the table (no goal/grasp yet)."""

    @property
    def _default_human_render_camera_configs(self):
        # zoom the preview camera onto the cube workspace (parent's view is wide)
        pose = sapien_utils.look_at(eye=[0.4, 0.4, 0.45], target=[-0.05, 0.0, 0.08])
        return CameraConfig("render_camera", pose, 512, 512, 1, 0.01, 100)

    def _load_scene(self, options: dict):
        # rebuild the table + robot scaffolding the parent would have made
        self.table_scene = TableSceneBuilder(
            self, robot_init_qpos_noise=self.robot_init_qpos_noise
        )
        self.table_scene.build()

        self.cubes = []
        for name, color in CUBE_COLORS:
            cube = actors.build_cube(
                self.scene,
                half_size=self.cube_half_size,
                color=color,
                name=f"cube_{name}",
                initial_pose=sapien.Pose(p=[0, 0, self.cube_half_size]),
            )
            self.cubes.append(cube)
        # keep parent code paths that reference a single `self.cube` happy
        self.cube = self.cubes[0]

    def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
        with torch.device(self.device):
            b = len(env_idx)
            self.table_scene.initialize(env_idx)

            half = self.cube_spawn_half_size          # spawn region half-extent
            min_sep = self.cube_half_size * 2 * 1.6   # center-to-center spacing

            # Rejection-sample non-overlapping xy per environment. Uses torch.rand,
            # which ManiSkill seeds on reset -> same seed reproduces the layout.
            n = len(self.cubes)
            positions = torch.zeros((n, b, 2))
            for e in range(b):
                chosen: list[torch.Tensor] = []
                for _ in range(n):
                    xy = (torch.rand(2) * 2 - 1) * half
                    for _try in range(100):
                        if all(torch.linalg.norm(xy - c) >= min_sep for c in chosen):
                            break
                        xy = (torch.rand(2) * 2 - 1) * half
                    chosen.append(xy)
                for ci, xy in enumerate(chosen):
                    positions[ci, e] = xy

            for ci, cube in enumerate(self.cubes):
                xyz = torch.zeros((b, 3))
                xyz[:, :2] = positions[ci]
                xyz[:, 2] = self.cube_half_size
                qs = randomization.random_quaternions(b, lock_x=True, lock_y=True)
                cube.set_pose(Pose.create_from_pq(xyz, qs))

            # Pick the target cube from the SAME seeded RNG (one more draw, like
            # the positions). Same seed -> same target, so it reproduces on replay
            # without any side-channel metadata.
            self.target_id = torch.randint(0, len(self.cubes), (b,))

    def target_color(self, env_i: int = 0) -> str:
        """Color name of the current target (for building instructions)."""
        return CUBE_COLORS[int(self.target_id[env_i])][0]

    def label_metadata(self) -> dict:
        """Dataset-level decoder for the integer labels in obs/extra.

        The consumer (h5_add_images) writes whatever this returns into the
        dataset's JSON sidecar, so `target_id=2 -> "blue"` is recoverable from
        the data alone without importing this code. Generic contract: any env
        that defines this method gets its mapping recorded; envs that don't
        (e.g. PickCube) are unaffected. Maps an obs field name to the list of
        label strings indexed by that field's integer value.
        """
        return {"target_id": [name for name, _ in CUBE_COLORS]}

    def instruction_template(self) -> str:
        """언어 명령 틀 — {target_id} 는 label_metadata 로 색 이름 치환. 학습(h5_to_lerobot)과
        평가(gr00t_eval)가 이 하나만 읽어 문구가 어긋나지 않게 한다(단일 출처)."""
        return "pick up the {target_id} cube"

    def evaluate(self):
        # success = the TARGET cube is grasped and lifted clear of the table
        grasped = torch.stack(
            [self.agent.is_grasping(c) for c in self.cubes], dim=0)   # (n_cubes, b)
        heights = torch.stack(
            [c.pose.p[:, 2] for c in self.cubes], dim=0)              # (n_cubes, b)
        ar = torch.arange(self.num_envs, device=self.device)
        idx = self.target_id.to(self.device)
        tgt_grasped = grasped[idx, ar]
        tgt_lifted = heights[idx, ar] > (self.cube_half_size + 0.04)
        return {"success": tgt_grasped & tgt_lifted, "is_grasped": tgt_grasped}

    # The parent's dense reward references a goal_site this task doesn't have.
    # Reward is unused for dataset generation, so neutralize it.
    def compute_dense_reward(self, obs, action, info):
        return torch.zeros(self.num_envs, device=self.device)

    def compute_normalized_dense_reward(self, obs, action, info):
        return self.compute_dense_reward(obs, action, info)

    def _get_obs_extra(self, info: dict):
        obs = dict(
            tcp_pose=self.agent.tcp_pose.raw_pose,
            target_id=self.target_id,                       # which cube to pick
        )
        # all cube poses (so a policy/labeler can resolve the target's location)
        all_poses = torch.stack([c.pose.raw_pose for c in self.cubes], dim=0)  # (n,b,7)
        idx = self.target_id.to(all_poses.device)
        obs["target_pose"] = all_poses[idx, torch.arange(self.num_envs)]       # (b,7)
        for (name, _), cube in zip(CUBE_COLORS, self.cubes):
            obs[f"{name}_cube_pose"] = cube.pose.raw_pose
        return obs


@register_env("ColoredCubeInBowl-v1", max_episode_steps=100)
class ColoredCubeInBowlEnv(PickCubeEnv):
    """Pick the seed-chosen colored cube and drop it into a bowl.

    Same language-conditioned setup as ThreeColoredCubes (three red/green/blue
    cubes, a seeded target), but the goal is *place into a container* rather than
    lift: success = the target cube comes to rest inside the bowl, released and
    static. The bowl is a shallow box-walled tray (self-contained: no mesh asset
    download, no mesh-collision IK surprises). Cubes spawn in the near (-x) zone,
    the bowl in the far (+x) zone, so they never overlap and both stay reachable.

    Reuses the exact contracts the consumer skills follow: primary camera
    'base_camera' (inherited from PickCubeEnv), tcp_pose in _get_obs_extra,
    evaluate() -> {"success": ...}, and label_metadata() for the color decoder.
    """

    # bowl tray geometry (half-extents, metres)
    bowl_wall_half = 0.005       # half thickness of floor/walls
    bowl_inner_half = 0.06       # half side of the inner square (fits a 0.04 cube)
    bowl_wall_height_half = 0.025  # half height of the walls

    @property
    def _default_human_render_camera_configs(self):
        pose = sapien_utils.look_at(eye=[0.4, 0.4, 0.5], target=[0.0, 0.0, 0.08])
        return CameraConfig("render_camera", pose, 512, 512, 1, 0.01, 100)

    def _build_bowl(self):
        t = self.bowl_wall_half
        inner = self.bowl_inner_half
        wall_h = self.bowl_wall_height_half
        mat = sapien.render.RenderMaterial(base_color=[0.75, 0.6, 0.4, 1.0])
        builder = self.scene.create_actor_builder()

        # floor plate: rests on the table (bottom face at z=0, top at z=2t)
        floor_half = [inner + 2 * t, inner + 2 * t, t]
        builder.add_box_collision(sapien.Pose([0, 0, t]), floor_half)
        builder.add_box_visual(sapien.Pose([0, 0, t]), floor_half, material=mat)

        # four upright walls sitting on the floor plate
        wz = 2 * t + wall_h
        walls = [
            (sapien.Pose([inner + t, 0, wz]), [t, inner + 2 * t, wall_h]),   # +x
            (sapien.Pose([-inner - t, 0, wz]), [t, inner + 2 * t, wall_h]),  # -x
            (sapien.Pose([0, inner + t, wz]), [inner + 2 * t, t, wall_h]),   # +y
            (sapien.Pose([0, -inner - t, wz]), [inner + 2 * t, t, wall_h]),  # -y
        ]
        for pose, half in walls:
            builder.add_box_collision(pose, half)
            builder.add_box_visual(pose, half, material=mat)

        builder.initial_pose = sapien.Pose(p=[0, 0, 0])
        return builder.build_kinematic(name="bowl")

    def _load_scene(self, options: dict):
        self.table_scene = TableSceneBuilder(
            self, robot_init_qpos_noise=self.robot_init_qpos_noise
        )
        self.table_scene.build()

        self.cubes = []
        for name, color in CUBE_COLORS:
            cube = actors.build_cube(
                self.scene,
                half_size=self.cube_half_size,
                color=color,
                name=f"cube_{name}",
                initial_pose=sapien.Pose(p=[0, 0, self.cube_half_size]),
            )
            self.cubes.append(cube)
        self.cube = self.cubes[0]   # keep parent code paths happy
        self.bowl = self._build_bowl()

    def _initialize_episode(self, env_idx: torch.Tensor, options: dict):
        with torch.device(self.device):
            b = len(env_idx)
            self.table_scene.initialize(env_idx)

            # cubes in the near (-x) zone; rejection-sample non-overlapping xy.
            min_sep = self.cube_half_size * 2 * 1.8
            n = len(self.cubes)
            positions = torch.zeros((n, b, 2))
            for e in range(b):
                chosen: list[torch.Tensor] = []
                for _ in range(n):
                    xy = torch.tensor([
                        float(torch.rand(1)) * 0.10 - 0.12,   # x in [-0.12, -0.02]
                        float(torch.rand(1)) * 0.24 - 0.12,   # y in [-0.12,  0.12]
                    ])
                    for _try in range(100):
                        if all(torch.linalg.norm(xy - c) >= min_sep for c in chosen):
                            break
                        xy = torch.tensor([
                            float(torch.rand(1)) * 0.10 - 0.12,
                            float(torch.rand(1)) * 0.24 - 0.12,
                        ])
                    chosen.append(xy)
                for ci, xy in enumerate(chosen):
                    positions[ci, e] = xy

            for ci, cube in enumerate(self.cubes):
                xyz = torch.zeros((b, 3))
                xyz[:, :2] = positions[ci]
                xyz[:, 2] = self.cube_half_size
                qs = randomization.random_quaternions(b, lock_x=True, lock_y=True)
                cube.set_pose(Pose.create_from_pq(xyz, qs))

            # bowl in the far (+x) zone, drawn from the same seeded RNG.
            bowl_xyz = torch.zeros((b, 3))
            bowl_xyz[:, 0] = torch.rand(b) * 0.08 + 0.02   # x in [0.02, 0.10]
            bowl_xyz[:, 1] = torch.rand(b) * 0.16 - 0.08   # y in [-0.08, 0.08]
            self.bowl.set_pose(Pose.create_from_pq(bowl_xyz))

            # one more seeded draw -> the target cube (reproduces on replay)
            self.target_id = torch.randint(0, len(self.cubes), (b,))

    def target_color(self, env_i: int = 0) -> str:
        return CUBE_COLORS[int(self.target_id[env_i])][0]

    def label_metadata(self) -> dict:
        return {"target_id": [name for name, _ in CUBE_COLORS]}

    def instruction_template(self) -> str:
        """언어 명령 틀 — {target_id} 는 label_metadata 로 색 이름 치환. 학습(h5_to_lerobot)과
        평가(gr00t_eval)가 이 하나만 읽어 문구가 어긋나지 않게 한다(단일 출처)."""
        return "put the {target_id} cube in the bowl"

    def evaluate(self):
        ar = torch.arange(self.num_envs, device=self.device)
        idx = self.target_id.to(self.device)

        cube_p = torch.stack([c.pose.p for c in self.cubes], dim=0)[idx, ar]   # (b,3)
        bowl_p = self.bowl.pose.p                                              # (b,3)
        offset = cube_p - bowl_p
        # target cube centred over the bowl floor and resting low (not held up)
        xy_in = torch.linalg.norm(offset[:, :2], axis=1) <= (
            self.bowl_inner_half - self.cube_half_size
        )
        z_low = (offset[:, 2] >= 0.0) & (offset[:, 2] <= 0.06)
        in_bowl = xy_in & z_low

        grasped = torch.stack(
            [self.agent.is_grasping(c) for c in self.cubes], dim=0)[idx, ar]   # (b,)
        cube_static = torch.stack(
            [c.is_static(lin_thresh=1e-2, ang_thresh=0.5) for c in self.cubes],
            dim=0)[idx, ar]
        success = in_bowl & (~grasped) & cube_static
        return {"success": success, "in_bowl": in_bowl, "is_grasped": grasped}

    def compute_dense_reward(self, obs, action, info):
        return torch.zeros(self.num_envs, device=self.device)

    def compute_normalized_dense_reward(self, obs, action, info):
        return self.compute_dense_reward(obs, action, info)

    def _get_obs_extra(self, info: dict):
        obs = dict(
            tcp_pose=self.agent.tcp_pose.raw_pose,
            target_id=self.target_id,
            bowl_pose=self.bowl.pose.raw_pose,
        )
        all_poses = torch.stack([c.pose.raw_pose for c in self.cubes], dim=0)  # (n,b,7)
        idx = self.target_id.to(all_poses.device)
        obs["target_pose"] = all_poses[idx, torch.arange(self.num_envs)]       # (b,7)
        for (name, _), cube in zip(CUBE_COLORS, self.cubes):
            obs[f"{name}_cube_pose"] = cube.pose.raw_pose
        return obs
