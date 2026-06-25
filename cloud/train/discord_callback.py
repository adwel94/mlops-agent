"""GR00T 학습 진행을 Discord 로 push 하는 TrainerCallback.

GR00T 는 Trainer 를 experiment.run() 안에 감춰서 외부에서 add_callback 을 못 한다.
그래서 _gr00t_train.py 가 Gr00tTrainer.__init__ 을 몽키패치해 이 콜백을 끼운다.
HF 공식 콜백(on_step_end)을 그대로 타므로 stdout 파싱 없이 견고하다.

webhook URL 은 env(RUNPOD_WEBHOOK_URL 등)에서 utils.discord 가 읽는다.
"""

import time

from transformers import TrainerCallback

from utils.discord import send_progress_notification, send_discord, DiscordChannel


class DiscordProgressCallback(TrainerCallback):
    def __init__(self, run_name: str, hook_steps: int = 20,
                 channel: DiscordChannel = DiscordChannel.PIPELINE):
        self.run_name = run_name
        self.hook_steps = max(1, hook_steps)
        self.channel = channel
        self.start_time = None

    def on_train_begin(self, args, state, control, **kwargs):
        self.start_time = time.time()

    def on_step_end(self, args, state, control, **kwargs):
        if state.global_step % self.hook_steps != 0 or state.global_step == 0:
            return
        # 최근 loss (있으면) 덧붙임 — log_history 마지막 엔트리에서.
        loss = None
        for entry in reversed(state.log_history or []):
            if "loss" in entry:
                loss = entry["loss"]
                break
        title = self.run_name + (f"  loss={loss:.4f}" if loss is not None else "")
        send_progress_notification(
            title=title,
            current_step=state.global_step,
            total_steps=state.max_steps,
            start_time=self.start_time or time.time(),
            channel=self.channel,
        )

    def on_train_end(self, args, state, control, **kwargs):
        send_discord(
            f"🏁 *[train] 스텝 종료* `{self.run_name}` — {state.global_step}/{state.max_steps} steps",
            channel=self.channel,
        )
