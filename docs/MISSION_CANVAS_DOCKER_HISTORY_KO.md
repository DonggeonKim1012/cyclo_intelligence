# CE 실행 코드 복구 이력

## 2026-10-27 — dg-branch 기반 기능별 복구

- 기준 이력: DonggeonKim1012/cyclo_intelligence dg-branch, a7037281a9b49ea5847573606f63cf0b73355471.
- 복구 브랜치: recovery/ce-runtime-20261027. 과거 변경 시점을 재현한 것이 아니라 현재 코드를 기능별로 나눈 복구 커밋이다.
- 원본: 실행 중인 cyclo_merge_20261020의 /validation/cyclo_ws/src/cyclo_intelligence.
- 컨테이너 이미지: sha256:f52960f54b72cc48e8d6d68e331299d99c25f313a053310ca530d0b25f46d4a0. 컨테이너의 후속 수정은 이 원래 이미지 태그만으로 재현되지 않는다.
- 증상/확인된 원인: src와 설치된 Python 코드가 7개 파일에서 달랐으며 2개 파일은 설치 경로에만 있었다. 실행 런처는 install/setup.bash를 사용하므로 설치 버전을 아래 소스 경로로 복구했다.
- 변경 방식: 실행 파일 내용과 실행 권한을 보존하고 Git 객체 및 별도 브랜치에만 기록했다. 기존 호스트 작업 트리와 그 미커밋 변경은 유지했다. 컨테이너 재시작·재배포 및 로봇 동작은 수행하지 않았다.

### 설치 경로에서 복구한 실행 코드

- `orchestrator/orchestrator/bt/actions/arm_trajectory_replay.py` ← `/validation/cyclo_ws/install/orchestrator/lib/python3.12/site-packages/orchestrator/bt/actions/arm_trajectory_replay.py`
- `orchestrator/orchestrator/bt/actions/aruco_dock.py` ← `/validation/cyclo_ws/install/orchestrator/lib/python3.12/site-packages/orchestrator/bt/actions/aruco_dock.py`
- `orchestrator/orchestrator/bt/actions/base_move.py` ← `/validation/cyclo_ws/install/orchestrator/lib/python3.12/site-packages/orchestrator/bt/actions/base_move.py`
- `orchestrator/orchestrator/bt/actions/dock_retreat.py` ← `/validation/cyclo_ws/install/orchestrator/lib/python3.12/site-packages/orchestrator/bt/actions/dock_retreat.py`
- `orchestrator/orchestrator/bt/actions/joint_control.py` ← `/validation/cyclo_ws/install/orchestrator/lib/python3.12/site-packages/orchestrator/bt/actions/joint_control.py`
- `orchestrator/orchestrator/bt/bt_node.py` ← `/validation/cyclo_ws/install/orchestrator/lib/python3.12/site-packages/orchestrator/bt/bt_node.py`
- `orchestrator/orchestrator/bt/docking_retreat.py` ← `/validation/cyclo_ws/install/orchestrator/lib/python3.12/site-packages/orchestrator/bt/docking_retreat.py`
- `orchestrator/orchestrator/bt/docking_runtime.py` ← `/validation/cyclo_ws/install/orchestrator/lib/python3.12/site-packages/orchestrator/bt/docking_runtime.py`
- `orchestrator/orchestrator/bt/node_registry.py` ← `/validation/cyclo_ws/install/orchestrator/lib/python3.12/site-packages/orchestrator/bt/node_registry.py`

### 포함 범위와 남은 제약

- src의 소스·테스트·설정·문서를 포함한다. 로그 이미지, 캐시, 빌드 산출물 및 .before-* 사본은 제외한다.
- CE에 체크아웃되지 않은 하위 저장소 3개의 기존 gitlink를 유지한다. 하위 저장소의 실행 파일 전체를 복구했다는 뜻은 아니다.
- UI는 CE src의 버전이다. 별도 cyclo_ui_battery_20261022가 서비스하는 번들과 같은 버전이라고 검증하지 않았다. 호스트에만 있는 추가 UI 변경은 섞지 않았다.
- ad/Zenoh 코드, 외부 Python/ROS 패키지 수정, 호스트 /deployment 서비스·s6 바이너리·환경 변수·데이터·장치 설정은 이 저장소 복구 범위 밖이다. 전체 컨테이너 재생성에는 기존 이미지 스냅샷과 bind mount 자료가 계속 필요하다.
- 원본 Python 115개와 설치 경로를 비교하여 차이와 설치 전용 파일을 확인했다. 소스와 대응되는 install/share의 launch·설정 파일에는 차이가 없었다.
- 최종 Git 트리는 원본 src에 위 9개 설치 버전을 적용한 대상과 파일 내용·Git 모드를 대조한다. 기능별 중간 커밋은 전체 시스템으로 각각 실행 검증한 릴리스가 아니다.
- 이번 작업은 코드 보존이며 새 동작을 구현하거나 배포하는 작업이 아니다. 테스트가 실패하더라도 실행 코드를 임의로 고쳐 원본과 달라지게 하지 않는다.

### 기능별 커밋

- feat(runtime): recover policy control, rail execution and inference contracts
- feat(groot): recover model overlays and cached inference processing
- feat(qwen): recover reasoning engine and LoRA training workflows
- feat(sam2): recover segmentation serving and class adaptation
- fix(recording): recover recorder monitoring and preview service settings
- feat(docking): recover ArUco docking, retreat and waypoint return
- feat(bt): recover motion replay, base movement and supervised task execution
- feat(collection): recover episode, frame and observation APIs
- feat(perception-api): recover reasoning, annotation and segmentation workflows
- feat(autonomy-api): recover mission operation and navigation coordination
- feat(bt-ui): recover action canvas and behavior parameter editors
- feat(mission-ui): recover map workspace, mission design and navigation controls
- feat(autonomy-ui): recover collection, annotation and operation workspace
- feat(ui): recover workspace integration and shared client infrastructure
- chore(deployment): recover container and SH5 interoperability configuration
- docs: record CE runtime recovery provenance and verification scope

### 복구 검증 결과

- 복구 대상 Python 360개 문법 검사 통과.
- 원본 컨테이너 파일 1,470개(설치 버전 9개 포함)를 내용 해시·Git 실행 모드로 다시 비교: 차이 0개.
- 최종 트리: 실행 소스·설정·기존 문서 등 1,470개 + 기존 gitlink 3개 + 이 복구 문서 1개.
- 기존 순수 로직 테스트: test_collection_episode_contract.py, test_collection_review_counts.py, test_execution_state.py — 33 passed.
- 테스트에는 로봇 동작·컨테이너 재시작·UI 전체 빌드·하위 저장소 빌드 검증이 포함되지 않는다.
