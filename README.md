# Cyclo Intelligence

Cyclo Intelligence is a Physical AI platform for data recording, dataset
conversion, policy training, inference, and robot execution with AI Worker.
For detailed usage instructions, please refer to the documentation below.
  - [Documentation for AI Worker Imitation Learning](https://docs.robotis.com/docs/systems/aiworker/imitation_learning/)

To install Cyclo Intelligence:

```bash
curl -fsSL https://raw.githubusercontent.com/ROBOTIS-GIT/cyclo_intelligence/main/install.sh | bash
```

On ROBOTIS robot PCs whose host name starts with `ffw`, the installer places
the checkout under `/mnt/ssd/cyclo_intelligence` and bind-mounts it at
`~/cyclo_intelligence`. On other PCs, it installs directly under
`~/cyclo_intelligence`.

To learn more about the ROS 2 packages for the AI Worker, visit:
  - [AI Worker ROS 2 Packages](https://github.com/ROBOTIS-GIT/ai_worker)

To explore our open-source platforms in a simulation environment, visit:
  - [Simulation Models](https://github.com/ROBOTIS-GIT/robotis_mujoco_menagerie)

For usage instructions and demonstrations of the AI Worker, check out:
  - [Tutorial Videos](https://www.youtube.com/@ROBOTISOpenSourceTeam)

To access datasets and pre-trained models for our open-source platforms, see:
  - [AI Models & Datasets](https://huggingface.co/ROBOTIS)

To use Docker images for running Cyclo Intelligence, visit:
  - [Docker Images](https://hub.docker.com/u/robotis)

For the SH5 tactile GR00T integration, see the
[build and inference guide](docs/2026-10-06_09-44-52_sh5_tactile_groot_inference.md).

## LG2 mini leader + SH5: fork 간 클린 배포 재현

이 절은 `DonggeonKim1012/cyclo_intelligence:dg-branch`와
`DonggeonKim1012/ai_worker:lg2-recording-controls-20261014`의 변경 커밋을 **함께** 배포하는 방법이다.
위 upstream `install.sh`는 이 fork 조합의 재현 명령이 아니다. 두 저장소의 커밋 SHA를 고정하고
기존 이미지/ROS workspace와 분리해 빌드한다. AI 저장소 README의
“LG2 mini leader + SH5: 독립 클린 빌드와 배포”를 먼저 읽는다.
대상은 Jetson Orin ARM64/L4T 36.4, Jazzy이며 일반 로봇용 설치 절차를 대체하지 않는다.

### 1. 소스·upstream 의존성·장비 설정

AI README의 1~2단계를 먼저 실행한다. 두 fork와 `robotis_interfaces`를 새 디렉터리에 clone하고,
`AI_REF`, `CYCLO_REF`에 40자리 커밋 SHA를 지정한다. AI 소스 대신 upstream `jazzy`를 clone하는
기존 AI Dockerfile을 사용하지 않는다. upstream 의존성만 AI 저장소의
`docker/lg2-sh5/sources.repos`에 기록된 SHA로 가져온다.

```text
$DEPLOY_ROOT/
  ai_ws/src/ai_worker/                # fork의 고정 커밋
  ai_ws/src/<upstream dependencies>/  # sources.repos의 고정 커밋
  cyclo_ws/src/cyclo_intelligence/     # 이 저장소의 고정 커밋
  cyclo_ws/src/robotis_interfaces/     # AI와 같은 7a5670cb... 커밋
  hardware/rs_serial.yaml
  real-data/ai/                       # 프리셋·ROS 로그
  real-data/cyclo/.web-relay/          # 데이터·API/relay 로그
  evidence/                          # 커밋 목록·배포 기록
```

당시 장비는 왼쪽/오른쪽 D405 `335122271364`/`335122273200`, ZED-M `13018209`,
왼쪽 OpenRB `00000002`, 오른쪽 OpenRB `20FBBD68503059384C2E3120FF08322D`였다.
AI README에 by-id → `/dev/follower`, `/dev/left_leader`, `/dev/right_leader`, ORIN 두 포트 매핑,
RealSense 문자열 따옴표, ZED SDK·보정 파일과 checksum을 기록했다.
**다른 장비에서는 물리적 좌우를 확인하고 값을 바꾼다.** Cyclo에는 USB 장치를 직접 넘기지 않는다.

### 2. 의존성 이미지·ROS·UI 빌드

AI README에서 만든 `DEPLOY_ROOT`를 사용한다. 아래 명령은 운영 노드를 실행하지 않는다.
Docker와 Git을 사용할 수 있는 호스트 사용자로 실행한다.

```bash
export CYCLO_IMAGE="local/cyclo-lg2-sh5:$(git -C "$DEPLOY_ROOT/cyclo_ws/src/cyclo_intelligence" rev-parse --short=12 HEAD)"
export CYCLO_TOOLS="$DEPLOY_ROOT/cyclo_ws/src/cyclo_intelligence/docker/lg2-sh5"
docker build --no-cache --progress=plain \
  -f "$CYCLO_TOOLS/Dockerfile" -t "$CYCLO_IMAGE" "$DEPLOY_ROOT"

# 새 workspace만 허용. 기존 build/install/log가 있으면 삭제하지 않고 실패함.
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$DEPLOY_ROOT:/validation" --entrypoint /usr/bin/env "$CYCLO_IMAGE" \
  -i HOME=/tmp LANG=C.UTF-8 PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  bash --noprofile --norc /validation/cyclo_ws/src/cyclo_intelligence/docker/lg2-sh5/build-ros.sh

# ARM64 Node 22 이미지. npm ci는 lockfile을 사용하고 새 checkout의 UI를 빌드함.
export NODE_IMAGE='node@sha256:62e4daa6819762bbd3072af77cc282ab72c631c4aed30dd7980192babaf385b3'
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e CI=false \
  -e GENERATE_SOURCEMAP=false \
  -v "$DEPLOY_ROOT:/validation" \
  -w /validation/cyclo_ws/src/cyclo_intelligence/orchestrator/ui \
  "$NODE_IMAGE" bash -lc 'npm ci --legacy-peer-deps && npm run build'
```

ROS 빌드에는 `/opt/ros/jazzy`만 source하고 호스트 overlay를 사용하지 않는다.
UI의 `build/`는 이 새 checkout 안에 생성된다. 기존 UI build를 가져오지 않는다.
Cyclo 이미지에는 ROS/Python 의존성과 `/opt/validation-venv`를 만든다.
이미지 내 `/dependency-src`는 rosdep 설치용 복사본일 뿐 실제 실행 경로가 아니다.
실행은 다음 단계의 `/validation/cyclo_ws/install` **bind mount**를 사용한다.

PyTorch 2.7.0, pyarrow 24.0.0 등을 설치하지만 정책 추론 GPU/backend 컨테이너까지 구성하는 절차는 아니다.
apt/rosdep와 일부 pip 의존성이 완전히 고정되지는 않았으므로 패키지 목록과 이미지 아카이브도 보관한다.
`--no-cache`는 빌드 레이어 재사용을 막는 옵션이지 모든 외부 패키지를 버전 고정하는 옵션이 아니다.

### 3. 컨테이너·브라우저 구성

AI README의 이미지 빌드 및 `ai_worker_lg2_sh5` 생성까지 먼저 완료한다.
AI는 `--network none`이고 Cyclo는 그 네트워크 namespace를 공유한다.
기존 시스템 ROS graph나 다른 AI Worker와 섞이지 않도록 host network를 ROS 컨테이너에 쓰지 않는다.
웹 프록시만 host network로 명시적 포트를 연다. 두 ROS 환경은 domain 174 + Zenoh router를 공유한다.

`docker/lg2-sh5/nginx.conf`의 `192.168.6.2`는 당시 로봇 PC의 LAN IP다.
다른 IP라면 저장소 원본 대신 배포용 복사본을 편집한다. 아래 `web-config`는 환경별 설정이므로
배포 기록에 함께 보관한다. 포트가 이미 점유되어 있으면 기존 서비스를 임의 종료하지 말고
운영자와 중단/포트 변경을 정한다. 포트를 바꾸면 nginx와 `cyclo-config.js` 양쪽을 맞춘다.

```bash
mkdir -p "$DEPLOY_ROOT/web-config" "$DEPLOY_ROOT/real-data/cyclo/.web-relay"
cp "$CYCLO_TOOLS/nginx.conf" "$CYCLO_TOOLS/cyclo-config.js" "$DEPLOY_ROOT/web-config/"
# 필요하면 web-config/nginx.conf의 192.168.6.2를 실제 로봇 IP로 수정
ss -lnt

docker run -d --name cyclo_lg2_sh5 --network container:ai_worker_lg2_sh5 \
  -v "$DEPLOY_ROOT:/validation:ro" \
  -v "$DEPLOY_ROOT/real-data/cyclo:/workspace" "$CYCLO_IMAGE"

# API + Unix socket relay만 실행. follower/leader는 자동 실행하지 않음.
docker exec -d cyclo_lg2_sh5 env -i HOME=/workspace LANG=C.UTF-8 \
  PATH=/opt/validation-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  bash --noprofile --norc /validation/cyclo_ws/src/cyclo_intelligence/docker/lg2-sh5/start-internal.sh

# 검증 환경의 nginx 이미지. 원격에서 확보할 수 없으면 보관한 image tar를 load한다.
export WEB_IMAGE='nginx@sha256:ed84151ed2d47ef93c0939eb9b9754c6990db6092cd2081e11988a47a83d47ea'
# nginx -t는 listen 주소도 검사한다. 격리된 검사 컨테이너 안에서만 nonlocal bind를 허용.
docker run --rm --network none --sysctl net.ipv4.ip_nonlocal_bind=1 \
  -v "$DEPLOY_ROOT/web-config/nginx.conf:/etc/nginx/nginx.conf:ro" \
  "$WEB_IMAGE" nginx -t
docker run -d --name cyclo_lg2_sh5_web --network host \
  -v "$DEPLOY_ROOT/web-config/nginx.conf:/etc/nginx/nginx.conf:ro" \
  -v "$DEPLOY_ROOT/web-config:/web:ro" \
  -v "$DEPLOY_ROOT/cyclo_ws/src/cyclo_intelligence/orchestrator/ui/build:/ui:ro" \
  -v "$DEPLOY_ROOT/cyclo_ws/install/shared/share/shared/robot_configs:/robot-configs:ro" \
  -v "$DEPLOY_ROOT/real-data/cyclo:/workspace:ro" \
  -v "$DEPLOY_ROOT/real-data/cyclo/.web-relay:/relay:ro" "$WEB_IMAGE"
```

위 nginx digest는 당시 `nginx:stable-alpine` 이미지다. 이동하는 태그 대신 digest를 고정했다.
배포 시 image ID도 기록하고, 복제 시 같은 digest 또는 저장한 이미지 아카이브를 사용한다.
프록시는 HTTP/ROS bridge를 노출하므로 **신뢰하는 LAN에서만** 사용한다.
인증·TLS·인터넷 방화벽 구성은 이 예제에 포함되지 않는다. 공개 인터넷으로 포트 포워딩하지 않는다.
`/workspace` 파일도 브라우저에서 접근할 수 있으므로 비밀키/토큰을 이 디렉터리에 저장하지 않는다.

| 다른 PC에서 접속 | 내부 Cyclo 서비스 |
| --- | --- |
| `http://192.168.6.2:17080` | UI 및 `/api/` supervisor (7100) |
| `ws://192.168.6.2:17090` | ROS bridge (7090) |
| `http://192.168.6.2:7082` | 데이터/재생 (7082); localhost 테스트는 17082 |
| `http://192.168.6.2:17085` | web_video_server (7085) |
| `http://192.168.6.2:17086` | 카메라 preview (7086) |

이 구성은 옛 `:7080`이 아니라 **`:17080`**이다. 같은 LAN의 다른 PC에서 직접 접속하며 SSH tunnel은 필요 없다.
UI에서 로봇 PC의 IP와 SH5 (`ffw_sh5_rev1`)를 선택한다. 설정을 바꾼 뒤에는 강력 새로고침한다.
API/relay 로그는 `real-data/cyclo/.web-relay/{supervisor,relay}.log`에 있다.
Docker socket과 s6를 연결하지 않으므로 UI의 다른 컨테이너 시작/정지, 정책 backend 설치/실행 기능까지
제공하는 배포는 아니다. 녹화·카메라·프리셋·미니 리더 추종 상호운용 검증 범위다.
격리 네트워크에서는 Hugging Face 다운로드 등 인터넷 작업도 별도 구성이 필요하다.

### 4. 실행과 조작 계약

AI README의 4단계에 router, Cyclo, follower(init pose + camera), mini leader를 각각 켜는 명령이 있다.
Cyclo 명령만 다시 실행하려면 다음을 사용한다. 이미 실행 중이면 중복 실행하지 않는다.

```bash
docker exec -it cyclo_lg2_sh5 env -i HOME=/workspace LANG=C.UTF-8 \
  PATH=/opt/validation-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  bash --noprofile --norc /validation/cyclo_ws/src/cyclo_intelligence/docker/lg2-sh5/cyclo-command.sh
```

Cyclo의 SH5에서만 `/leader/hand_preset/status`를 받아 `control_profile`을 확인한다.
AI의 전용 recording launch가 `lg2_mini_sh5_recording`을 발행한 경우에만 다음 매핑을 적용한다.

| 입력 | LG2 mini + SH5 전용 모드 |
| --- | --- |
| 해당 쪽 조이스틱 짧은 클릭 | 해당 팔 teleop toggle (녹화 아님) |
| 오른쪽 조이스틱 긴 클릭 (2초) | 준비된 세션의 녹화 시작 / 저장 |
| 왼쪽 조이스틱 긴 클릭 (2초) | 녹화 취소 |
| 손 트리거 | 선택한 SH5 hand preset 보간; teleop 시작 명령 아님 |

프로필을 사용하지 않는 기존 로봇에서는 기존 오른쪽/왼쪽 녹화 매핑을 유지한다.
프로필이 활성화됐다가 3초 이상 status가 끊기면 legacy 매핑으로 즉시 되돌리지 않고 입력을 막는다.
Hand Preset Studio 역시 SH5 + 일치하는 프로필 + 신선한 status에서만 표시한다.
이 때문에 **새 Cyclo와 옛 AI 또는 그 반대 조합을 섞지 않는다.** 두 커밋과 UI를 함께 빌드한다.

기본 LG2 launch와 SG2/BG2 등 일반 경로에 전용 설정을 강제하지 않지만, 기존 fork의 다른 변경까지
upstream main과 완전히 같다는 의미는 아니다. 모든 기종의 실기기 회귀 검증은 별도다.
로봇 동작 검증 시에는 비상정지를 준비하고 리더/follower 자세를 맞춘 뒤 한쪽씩 짧은 클릭한다.
API 응답이나 ROS topic 존재만으로 실제 추종이 검증됐다고 판단하지 않는다.

### 5. 변경 내용·재현 기록

이번 상호운용 보완에서 AI는 SH5 7축 팔 trajectory, 독립 raw trigger 손 입력, 프리셋 status 형식,
전용 launch opt-in을 반영했다. Cyclo는 프로필 기반 녹화 입력 분기, stale 상태 보호,
Hand Preset Studio 표시 조건 및 연결 변경 시 status 초기화를 반영했다.
개발 과정에서 추가했던 AI의 hand preset 테스트 두 파일과 호스트 임시 검증 파일은 요청에 따라 제거했다.
기존의 무관한 테스트나 upstream SDK 테스트 전체를 삭제한 것은 아니다.

당시 실행한 대상은 `cyclo_clean_real_20261015`, 이미지 `local/interop-hardware-runtime:20261015`
(ID `sha256:6405094691176155f772cc9233f35312f69728d8ec83f876a6250996df2466d1`)였다.
호스트 `/home/robotis/interop-clean-20261015-YMDUC0`를 `/validation:ro`로 마운트하여
`/validation/cyclo_ws/install`을 실행했다. 코드/빌드 결과가 이미지에만 들어 있던 구성이 아니다.
동시에 실행한 AI는 `ai_worker_full_real_20261015`이며 생성 이미지와 사후 복사된 live 수정의 차이는
AI README에 명시했다. 현재 실행 중인 임의의 컨테이너를 이 당시 환경으로 간주하지 않는다.

실기기 추종·카메라 성공 확인 이후 scope 분리 변경에 대해 ROS/Python 및 UI 빌드 검증을 수행했다.
이번에 저장소에 묶은 전용 Dockerfile/배포 절차 전체의 새 이미지 빌드와 scope 분리 후 실기기 검증은
추가로 필요하다. README/커밋 작업만으로 운영 컨테이너가 업데이트되지는 않는다.

```bash
docker image inspect --format '{{.Id}} {{json .RepoDigests}}' "$CYCLO_IMAGE" "$WEB_IMAGE"
docker exec cyclo_lg2_sh5 /opt/validation-venv/bin/pip freeze
docker exec cyclo_lg2_sh5 dpkg-query -W
docker inspect --format '{{json .Mounts}}' cyclo_lg2_sh5
docker image save -o "$DEPLOY_ROOT/evidence/cyclo-runtime.tar" "$CYCLO_IMAGE"
docker image save -o "$DEPLOY_ROOT/evidence/cyclo-web.tar" "$WEB_IMAGE"
```

두 Git SHA, upstream 소스 SHA, UI/ROS 빌드 결과, 이미지 ID/아카이브, hardware/web-config,
워크스페이스와 사용자 데이터까지 함께 보관해야 동일 배포를 복구할 수 있다.
runtime 이미지 아카이브에는 bind mount의 코드·프리셋·녹화 데이터가 포함되지 않는다.
전체 환경변수/inspect에는 자격 증명이 포함될 수 있으므로 공개하지 않는다.
