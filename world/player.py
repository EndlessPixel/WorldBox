"""玩家：视角、移动、跳跃、重力、自动跳跃与相机晃动。"""

import math

from ursina import Vec3, camera, mouse

from . import config, i18n
from .storage import _save_number


class Player:
    def __init__(self, world, save_data=None):
        self.world = world
        self.pos = Vec3(config.WORLD_SIZE / 2, 0, config.WORLD_SIZE / 2)
        self.velocity_y = 0.0
        self.grounded = True
        self.current_eye = config.EYE_HEIGHT
        self.yaw = 45.0
        self.pitch = 0.0
        self.current_fov = config.BASE_FOV
        self.bob_phase = 0.0
        self.bob_amount = 0.0
        self.current_speed = 0.0
        self.crouching = False
        self.sprinting = False
        self.zooming = False
        self.moving = False
        self.notice = None   # 一次性提示（如掉出世界），由 Game 读取后清空
        camera.fov = config.BASE_FOV

        if save_data:
            self.pos.x = _save_number(save_data.get('x'), self.pos.x,
                                      config.PLAYER_RADIUS,
                                      config.WORLD_SIZE - config.PLAYER_RADIUS)
            self.pos.z = _save_number(save_data.get('z'), self.pos.z,
                                      config.PLAYER_RADIUS,
                                      config.WORLD_SIZE - config.PLAYER_RADIUS)
            self.yaw = _save_number(save_data.get('yaw'), self.yaw, -360000, 360000) % 360
            self.pitch = _save_number(save_data.get('pitch'), self.pitch, -89.0, 89.0)

        camera.position = self.pos + Vec3(0, self.current_eye, 0)
        camera.rotation_x = self.pitch
        camera.rotation_y = self.yaw

    def overlaps(self, x, y, z):
        """判断方块是否与玩家 AABB 身体重叠，避免把自己封进方块里。"""
        radius = config.PLAYER_RADIUS
        if not (x < self.pos.x + radius and x + 1 > self.pos.x - radius
                and z < self.pos.z + radius and z + 1 > self.pos.z - radius):
            return False
        feet = math.floor(self.pos.y + 0.001)
        head = math.floor(self.pos.y + self.current_eye - 0.001)
        return feet <= y <= head

    def update(self, keys, just_pressed, dt):
        # --- 鼠标视角 ---
        if mouse.locked:
            self.yaw += mouse.velocity[0] * config.MOUSE_SENSITIVITY
            self.pitch -= mouse.velocity[1] * config.MOUSE_SENSITIVITY
            self.pitch = max(-89.0, min(89.0, self.pitch))
        camera.rotation_y = self.yaw
        camera.rotation_x = self.pitch

        # --- 蹲下 / 疾跑 / 跳跃（上升沿） ---
        self.crouching = 'shift' in keys
        self.sprinting = 'ctrl' in keys and not self.crouching
        if 'space' in just_pressed and self.grounded:
            self.velocity_y = config.JUMP_SPEED
            self.grounded = False

        # --- C 键放大：平滑改变视场角 ---
        self.zooming = 'c' in keys
        target_fov = config.ZOOM_FOV if self.zooming else config.BASE_FOV
        self.current_fov += (target_fov - self.current_fov) * min(
            1.0, dt * config.FOV_LERP_SPEED)
        if abs(camera.fov - self.current_fov) > 0.01:
            camera.fov = self.current_fov

        # --- 水平移动（基于朝向） ---
        fwd = int('w' in keys) - int('s' in keys)
        side = int('d' in keys) - int('a' in keys)
        self.current_speed = 0.0
        if fwd or side:
            yr = math.radians(self.yaw)
            forward = Vec3(math.sin(yr), 0, math.cos(yr))
            right = Vec3(math.cos(yr), 0, -math.sin(yr))
            move = (forward * fwd + right * side).normalized()

            speed = (config.CROUCH_SPEED if self.crouching
                     else (config.SPRINT_SPEED if self.sprinting else config.WALK_SPEED))
            self.current_speed = speed
            delta_x, delta_z = move.x * speed * dt, move.z * speed * dt
            # 拆成小步，避免掉帧时一步跨过无支撑区/薄墙（穿模）
            steps = max(1, math.ceil(max(abs(delta_x), abs(delta_z)) / 0.05))
            step_x, step_z = delta_x / steps, delta_z / steps
            for _ in range(steps):
                next_x = max(config.PLAYER_RADIUS,
                             min(config.WORLD_SIZE - config.PLAYER_RADIUS,
                                 self.pos.x + step_x))
                next_z = max(config.PLAYER_RADIUS,
                             min(config.WORLD_SIZE - config.PLAYER_RADIUS,
                                 self.pos.z + step_z))

                # 台阶/阻挡检测：按玩家 AABB 覆盖的所有列判断脚部/头部格
                feet_cell = math.floor(self.pos.y + 0.001)
                foot_solid, head_solid = self.world.body_clearance(
                    next_x, next_z, feet_cell, config.PLAYER_RADIUS)

                # 潜行（Shift）：脚下 AABB 全部失去支撑时不许迈出去
                sneak_blocked = False
                if self.crouching and self.grounded:
                    next_support = self.world.support_height_at(
                        next_x, next_z, self.pos.y, config.PLAYER_RADIUS)
                    sneak_blocked = next_support < self.pos.y - 0.02

                if not foot_solid and not head_solid and not sneak_blocked:
                    self.pos.x, self.pos.z = next_x, next_z
                elif (self.grounded and not head_solid and not sneak_blocked
                      and config.AUTO_JUMP and config.AUTO_JUMP_HEIGHT >= 1.0):
                    # 1 格台阶：真实抛物线起跳跨过去（不瞬移）
                    self.velocity_y = max(
                        config.JUMP_SPEED,
                        math.sqrt(2 * config.GRAVITY * 1.25))
                    self.grounded = False
                    self.pos.x, self.pos.z = next_x, next_z
                else:
                    break

        # 世界边界：每帧钳制
        self.pos.x = max(config.PLAYER_RADIUS,
                         min(config.WORLD_SIZE - config.PLAYER_RADIUS, self.pos.x))
        self.pos.z = max(config.PLAYER_RADIUS,
                         min(config.WORLD_SIZE - config.PLAYER_RADIUS, self.pos.z))

        # --- 重力与方块支撑（整个 AABB 足迹，钻洞时不会被洞顶吸上去） ---
        ground_y = self.world.support_height_at(
            self.pos.x, self.pos.z, self.pos.y, config.PLAYER_RADIUS)
        if self.crouching and self.grounded and ground_y < self.pos.y - 0.02:
            # 潜行时脚下被挖空也保持当前高度，不会掉下去；松开 Shift 恢复重力
            self.velocity_y = 0
        else:
            self.velocity_y -= config.GRAVITY * dt
            self.pos.y += self.velocity_y * dt
            if self.pos.y <= ground_y:
                self.pos.y = ground_y
                self.velocity_y = 0
                self.grounded = True
            else:
                self.grounded = False

        # 掉出世界：低于底限就传送回出生点
        if self.pos.y <= config.FALL_LIMIT_Y:
            self.pos.x = config.WORLD_SIZE / 2
            self.pos.z = config.WORLD_SIZE / 2
            spawn_ground = self.world.ground_height_at(self.pos.x, self.pos.z)
            self.pos.y = max(0.0, spawn_ground) + 0.05
            self.velocity_y = 0
            self.grounded = True
            self.notice = i18n.t('notice.fell')

        # --- 眼高平滑过渡 ---
        target_eye = config.CROUCH_EYE_HEIGHT if self.crouching else config.EYE_HEIGHT
        self.current_eye += (target_eye - self.current_eye) * min(
            1.0, dt * config.EYE_LERP_SPEED)

        # --- 移动时的视角晃动（view_bob 可配置，0 关闭） ---
        self.moving = bool(fwd or side) and self.grounded
        self.bob_amount += ((1.0 if self.moving else 0.0) - self.bob_amount) * min(
            1.0, dt * 8)
        if self.moving and self.current_speed > 0:
            self.bob_phase += dt * 9.0 * (self.current_speed / config.WALK_SPEED)
        bob_y = math.sin(self.bob_phase) * config.VIEW_BOB * self.bob_amount
        bob_x = math.sin(self.bob_phase * 0.5) * config.VIEW_BOB * 0.4 * self.bob_amount
        yr = math.radians(self.yaw)
        camera.position = self.pos + Vec3(
            math.cos(yr) * bob_x,
            self.current_eye + bob_y,
            -math.sin(yr) * bob_x,
        )
