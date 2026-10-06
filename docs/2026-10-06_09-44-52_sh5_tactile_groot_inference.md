# SH5 tactile GR00T inference

Implementation record, 2026-10-06 KST. Branch:
`sync/a-first-feature-local-functions`, based on
`myfork/sync/a-first-feature-local-functions` at `7862e55` in
`DonggeonKim1012/cyclo_intelligence`. Ported from the SH5 integration commit
`1bd9df8` on `feature/sh5-tactile-groot`; no unrelated branch changes were imported.

## Source and checkpoint

Cyclo's GR00T submodule now selects the company-compatible integration commit
`56a695669260908f116bf88a8c8843d07bd7bae6`. The Dockerfiles copy this submodule
into `/gr00t` and check that `tactile_encoders.py` is present. There is no
training-repository symlink or runtime source mount.

The submodule URL is `https://github.com/DonggeonKim1012/Isaac-GR00T.git`.
The configured branch is `integrate/sh5-tactile`, verified at `56a6956`.
Normal submodule initialization uses this pinned commit; `update --remote`
follows the configured branch. Commit `.gitmodules` and the Cyclo gitlink
together. No image publication has been performed.

Use the complete Task000650 `checkpoint-200000` package, including weights,
model config, processor config, normalization statistics, and embodiment mapping.
Keep checkpoints outside the image under `docker/workspace/model/groot/`.
For transfer to another machine, produce and verify a SHA-256 manifest for the
complete package in a new staging directory before promotion.

## Input and output contract

The runtime reads `use_tactile` from the checkpoint and passes it to `Gr00tPolicy`.
The saved processor supplies the 256×256 image recipe and tactile normalization.
Use robot type `ffw_sh5_rev1` and acceleration mode `pytorch` or `tensorrt_dit`.

| Policy key | Cyclo group or sensor | Width |
| --- | --- | --- |
| left_arm | arm_left | 7 |
| right_arm | arm_right | 7 |
| left_hand | hand_left | 20 |
| right_hand | hand_right | 20 |
| tactile_left | tactile_left_hand_pressure | 45 |
| tactile_right | tactile_right_hand_pressure | 45 |

Joint states are selected by the configured joint names. The action chunk stays
in the policy's arm-left, arm-right, hand-left, hand-right order; LOAD returns
the corresponding Cyclo controller keys. The SH5 YAML explicitly admits that
ordered four-group layout in addition to the existing full recorded layout.
Head, lift, and base are absent from this model's commands. Recording is unchanged.

Each hand is flattened as named sensors `finger_l_sensor1..5` or
`finger_r_sensor1..5`, each with `Present Pressure 1..9`. Sensor array order is
canonicalized by name; unexpected pressure names, missing/duplicate sensors,
non-finite values, and invalid dimensions are rejected. No baseline subtraction,
mean pooling, clipping, or second normalization is applied. Latest received
pressure samples older than 200 ms are rejected; malformed callbacks invalidate
the cached sample. These are receipt-time freshness checks, not a new full
camera/joint/tactile synchronization guarantee.

Only the three checkpoint cameras are subscribed for SH5. Wrist rotations come
from the robot YAML and are applied once before the saved image processor.

## Build and select an image

Run on a Docker-capable target/build machine with the populated submodule.
For an Orin use ARM64 and the matching JetPack environment:

```bash
export ARCH=arm64
export CYCLO_GROOT_IMAGE=local/groot:sh5-tactile-56a6956-arm64
docker compose -f docker/docker-compose.yml build groot
```

For publishing, replace the image name with your registry namespace and a unique
version tag, then push after container verification. Set the same
`CYCLO_GROOT_IMAGE` in `docker/.env` on the robot. Compose passes it into the main
Cyclo container so the UI supervisor pulls/selects the same image as Compose.
Recreate the main Cyclo container to apply this environment change when no
robot job is running. The existing default ROBOTIS image remains the default
when the variable is unset; it is not the image to select for this tactile model.

Rebuild the main `cyclo_intelligence` image as well to include the updated
Cycle Home UI; rebuilding only `groot` does not update the frontend bundle.

After building, a non-actuating prediction can be run without the UI or robot
subscriptions (replace the model directory as appropriate):

```bash
docker compose -f docker/docker-compose.yml run --rm --no-deps \
  --entrypoint /gr00t/.venv/bin/python groot \
  /app/scripts/smoke_groot_n17.py \
  --model-path /workspace/model/groot/task000650/checkpoint-200000 \
  --robot-type ffw_sh5_rev1 \
  --synthetic-inference
```

The ARM64 command uses its venv Python; the AMD64 image uses `python`.
Expected decoded shape is `(40, 54)`. Then validate with recorded observations
and Cyclo's non-actuating preview before requesting powered operation. Loading
the image/checkpoint does not authorize a real robot rollout.

## Verified and outstanding

Latest update: the same GR00T image selects SG2 or SH5 from Cyclo's selected
`robot_type`. LOAD validates saved state/action keys and widths before robot
subscriptions: SG2's full example has 22 values; SH5 has 54 joint values and
optionally 90 raw tactile values encoded into 32 features. It never rewrites
checkpoint settings to force a different robot. The smoke script accepts
`--robot-type ffw_sg2_rev1` or `--robot-type ffw_sh5_rev1` for an offline check.

TensorRT compiles the DiT action network for the target GPU. VLM and tactile
encoding remain in PyTorch. Select TensorRT DiT and build the engine before
Start; the builder restores the tactile flag from the checkpoint. The command
inside the running ARM64 container is:

```bash
docker compose -f docker/docker-compose.yml exec groot \
  /gr00t/.venv/bin/python /app/runtime/prepare_trt_engine.py \
  --model-path /workspace/model/groot/task000650/checkpoint-200000 \
  --robot-type ffw_sh5_rev1
```

Build and validate the engine on the target GPU/software stack. Full-pipeline
TensorRT remains unsupported. Cycle Home is enabled for real SH5 GR00T sessions
in running or paused state. It acknowledges PAUSE, requests the existing SH5
`both_sticks_up` return, waits for matching completion, then permits a fresh Start.
Start dispatches the engine reset: model and TensorRT weights stay loaded,
the policy resets, and robot observations reconnect. Failed reconnection blocks
inference. Raw tactile pressure is not re-zeroed or baseline-subtracted.
The return pose belongs to robot bringup; it is not inferred from the model.
SG2 and simulation remain excluded from this SH5-specific home operation.

Latest focused validation: 17 engine/camera tests passed with mocked GPU
dependencies, including SG2/SH5 validation, tactile DiT engine preparation,
and successful/failed cycle resets. Five shared reset protocol/service tests
and 10 checks of the actual UI enablement expression also passed.
Historical counts below refer to the previous integration.

Verified after porting to the sync branch: 60 runtime/pressure/action-contract
and camera tests, 11 isolated legacy initial-pose tests, and 138 supervisor
tests (209 total). The original integration also passed 40 GR00T
tactile/processor tests on the earlier submodule pin. Legacy robot tests
run separately because their ROS stubs conflict in one pytest process.
Actual checkpoint tactile weights previously loaded strictly and
produced finite `(1, 1, 32)` latent output; saved tactile/256×256 processor
settings restored. The VLM builder was mocked for this processor check.

Docker is absent on this server. Image build, full model prediction in the
container, live message definitions, target latency, and robot validation remain
unverified. DiT TensorRT is enabled in source for tactile checkpoints, but
target numerical agreement and performance remain unverified. The image registry
namespace remains a user choice. ROS lifecycle tests need generated interface
messages; the React suite needs the frontend dependencies installed.

Primary implementation references: [runtime](../cyclo_brain/policy/groot/runtime/inference_engine.py),
[RobotClient](../cyclo_brain/sdk/robot_client/robot_client/robot_client.py),
[SH5 YAML](../shared/shared/robot_configs/ffw_sh5_rev1_config.yaml),
[Compose](../docker/docker-compose.yml), and
[supervisor](../docker/supervisor_api/app.py).
