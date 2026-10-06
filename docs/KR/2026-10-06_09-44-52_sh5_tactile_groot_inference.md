# SH5 tactile GR00T 추론

2026-10-06 KST 구현 기록. `DonggeonKim1012/cyclo_intelligence`의
`myfork/sync/a-first-feature-local-functions` (`7862e55`)을 기반으로 한
`sync/a-first-feature-local-functions` 브랜치에 적용했다.
`feature/sh5-tactile-groot`의 SH5 통합 커밋 `1bd9df8`만 이식했으며,
관련 없는 다른 브랜치 변경은 포함하지 않았다.

## 소스와 체크포인트

Cyclo의 GR00T submodule은 fork의
`56a695669260908f116bf88a8c8843d07bd7bae6` 회사 호환 통합 커밋을 선택한다.
기존 Dockerfile이 이 소스를 `/gr00t`에 복사하며 tactile encoder 파일의
존재를 검사한다. 학습 저장소로 연결하는 symlink는 사용하지 않는다.

submodule URL은 `https://github.com/DonggeonKim1012/Isaac-GR00T.git`이다.
fork의 `integrate/sh5-tactile` 브랜치가 `56a6956`임을 확인했다.
다른 머신에서 재현하려면 `.gitmodules`, submodule gitlink,
Cyclo runtime 변경을 함께 커밋해야 한다. 이미지 배포는 수행하지 않았다.

Task000650의 `checkpoint-200000` 전체를 사용한다. 모델 가중치/config,
processor config, 정규화 통계, embodiment mapping을 함께 유지한다.
체크포인트는 이미지 밖 `docker/workspace/model/groot/`에 둔다.
다른 머신으로 전달할 때는 새 staging 경로에서 전체 패키지의 SHA-256
manifest를 검증한 후 승격한다.

## 입력 및 출력 계약

체크포인트의 `use_tactile`을 읽어 `Gr00tPolicy`에 전달한다.
저장된 processor가 256×256 이미지 전처리와 tactile 정규화를 복원한다.
로봇 종류는 `ffw_sh5_rev1`, 가속 모드는 `pytorch` 또는 `tensorrt_dit`를 선택한다.

| Policy 키 | Cyclo 그룹/센서 | 차원 |
| --- | --- | --- |
| left_arm | arm_left | 7 |
| right_arm | arm_right | 7 |
| left_hand | hand_left | 20 |
| right_hand | hand_right | 20 |
| tactile_left | tactile_left_hand_pressure | 45 |
| tactile_right | tactile_right_hand_pressure | 45 |

관절은 YAML의 이름 및 순서를 검증한다. action은 왼팔/오른팔/왼손/오른손
순서를 유지하며 LOAD 응답은 대응하는 Cyclo 제어 키를 반환한다.
SH5 YAML에 이 네 그룹의 정확한 순서를 추가 허용했다. 기존 전체 기록
레이아웃도 유지한다. 이 모델은 head/lift/base 명령을 포함하지 않는다.

각 손의 센서는 `finger_l_sensor1..5` 또는 `finger_r_sensor1..5`,
각 센서의 pressure는 `Present Pressure 1..9` 순서다.
센서 배열 순서는 이름으로 정렬하고 pressure 이름 불일치, 누락/중복,
비유한 값 및 잘못된 차원은 거부한다. baseline 차감, 평균 pooling,
clipping, 중복 정규화는 하지 않는다. 수신 후 200 ms가 지난 pressure는
거부하며 잘못된 메시지가 들어오면 이전 캐시도 무효화한다.
이는 수신 시간 기반 검사이며 카메라/관절/tactile 전체 동기화를 새로
보장하는 기능은 아니다.

SH5는 checkpoint의 세 카메라만 구독한다. 손목 영상 회전은 로봇 YAML에
따라 저장된 이미지 processor 이전에 한 번 적용한다.

## 빌드 및 선택

Docker가 있는 머신에 submodule 소스를 준비한다. Orin은 ARM64 및 해당
JetPack 환경을 사용한다.

```bash
export ARCH=arm64
export CYCLO_GROOT_IMAGE=local/groot:sh5-tactile-56a6956-arm64
docker compose -f docker/docker-compose.yml build groot
```

배포하려면 이미지 이름을 본인의 registry namespace 및 고유 버전 태그로
바꾸고 컨테이너 검증 후 push한다. 로봇의 `docker/.env`에도 같은
`CYCLO_GROOT_IMAGE`를 설정한다. Compose가 main Cyclo 컨테이너에 이 값을
전달하므로 UI supervisor도 같은 이미지를 사용한다. 로봇 작업이 없는
시점에 main 컨테이너를 재생성해야 환경 변수 변경이 반영된다.
변수가 없으면 기존 ROBOTIS 이미지가 기본값이며 tactile 모델에는 새
이미지를 명시적으로 선택해야 한다.

Cycle Home UI 변경을 반영하려면 main `cyclo_intelligence` 이미지도
다시 빌드한다. `groot` 이미지만 빌드하면 frontend는 갱신되지 않는다.

로봇 구독/구동 없이 컨테이너 추론을 검사하는 명령은 다음과 같다.

```bash
docker compose -f docker/docker-compose.yml run --rm --no-deps \
  --entrypoint /gr00t/.venv/bin/python groot \
  /app/scripts/smoke_groot_n17.py \
  --model-path /workspace/model/groot/task000650/checkpoint-200000 \
  --robot-type ffw_sh5_rev1 \
  --synthetic-inference
```

ARM64는 위 venv 경로, AMD64는 `python`을 사용한다. 예상 출력은
`(40, 54)`다. 이후 기록된 관측 replay 및 비구동 preview를 확인한다.
이미지/체크포인트 준비는 실제 로봇 구동 승인에 해당하지 않는다.

## 검증 및 미확인 사항

최신 변경: 동일 이미지에서 Cyclo가 선택한 robot_type으로 SG2/SH5를 검증한다.
SG2 기본 계약은 22차원, SH5는 관절 54차원과 선택적인 촉각 90차원이다.
체크포인트와 로봇의 키/차원이 다르면 센서 구독 전에 거부한다.
기존 smoke 스크립트의 --robot-type으로 비구동 검증도 가능하다.

TensorRT는 DiT 액션 네트워크만 대상 GPU용으로 컴파일한다. VLM과 촉각
인코더는 PyTorch에 남는다. UI에서 TensorRT DiT를 선택하고 엔진을 빌드한
후 Start한다. 빌더도 체크포인트의 tactile 설정을 복원한다.
full-pipeline TensorRT는 지원하지 않는다.
Cycle Home은 실제 SH5 GR00T 실행/일시정지 상태에서 활성화한다.
PAUSE 확인 → 기존 SH5 both_sticks_up 복귀 요청 → 일치하는 완료 응답 확인
→ 새로운 Start 흐름을 재사용한다. 복귀 자세는 로봇 bringup에서 정한다.
Start 시 engine reset이 모델/TRT 가중치를 유지하며 policy를 초기화하고
관측 구독을 재연결한다. 재연결 실패 시 추론을 차단한다.
raw tactile 압력의 영점 또는 baseline은 변경하지 않는다.
SG2/시뮬레이션에는 이 SH5 전용 복귀 기능을 활성화하지 않는다.
GPU 의존성을 mock한 engine/camera 테스트 17개, 공통 reset 경로 테스트
5개와 실제 UI 활성화 조건 검사 10개가 통과했다. 아래 횟수는 이전 통합 기록이다.

sync 브랜치 이식 후 CPU에서 runtime/pressure/action 계약 및 camera 60개,
기존 initial-pose 11개, supervisor 138개로 총 209개 테스트를 통과했다.
원래 통합에서 pin된 GR00T tactile/processor 40개도 통과했으며,
이 횟수는 이전 submodule pin에서의 검증 기록이다.
기존 ROS mock이 충돌하므로 initial-pose 테스트는 별도 프로세스로 실행했다.
이전 검증에서 실제 checkpoint의 tactile 가중치를 strict 로딩하고 유한한 `(1,1,32)`
latent 및 저장된 tactile/256×256 설정 복원을 확인했다. 이 processor
검증에서는 VLM builder를 mock했다.

이 서버에는 Docker가 없어 이미지 빌드, 컨테이너 전체 모델 추론,
실제 메시지 정의, 대상 장치 지연 시간 및 로봇 검증은 미완료다.
소스에서 tactile DiT TensorRT를 활성화했으나 대상 GPU의 수치 일치와 성능은
아직 검증하지 않았다. ROS 테스트는 생성된 interface 메시지, React 테스트는
frontend 의존성 설치가 필요하다.
registry 이름은 아직 정하지 않았다.

구현 근거: [runtime](../../cyclo_brain/policy/groot/runtime/inference_engine.py),
[RobotClient](../../cyclo_brain/sdk/robot_client/robot_client/robot_client.py),
[SH5 YAML](../../shared/shared/robot_configs/ffw_sh5_rev1_config.yaml),
[Compose](../../docker/docker-compose.yml),
[supervisor](../../docker/supervisor_api/app.py).
