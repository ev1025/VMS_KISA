# 라벨 대시보드(dash_v2) 구조

서버 `dash_v2/serve_kisa.py`(http.server, 포트 8890) + 브라우저 `dash_v2/js/*.js`(core → review → data → editor → main). 2026-09-10 리팩토링 기준.

## 데이터 규격 (2026-09-11) — 데이터셋별 하드코딩 금지

기준 파일 `configs/datasets.yaml`(git 관리, `data/학습데이터/datasets.yaml` 은 심링크) 하나가 원본 카테고리마다 `mode`(fire|person|none) · `media`(video|image) · `gt`(원본 정답 형식) · `classes`(원본 클래스 → 우리 클래스) · `use`(train|eval|none) 를 정한다.
코드는 **형식별 어댑터**(`dash_v2/gt_adapters.py`: yolo_txt · coco_json · voc_xml · kisa_xml · aihub171_xml · aihub_json · aihub71953_json)만 갖고, 새 데이터셋은 yaml 한 줄로 끝난다.

- 우리 클래스 규약(고정): fire 모드 0 불 · 1 연기 / person 모드 0 사람. 원본이 다르면 `classes` 로 뒤집거나 버린다(dfire 0↔1, azimjaan 구름 drop).
- 대시보드 `라벨 모드 → 적용` = yaml 의 `mode` 를 바꾼다(`POST /api/datasets`). `GET /api/datasets` 가 전체 규격, `/api/rawlabel` 은 어댑터를 거친 우리 규약의 YOLO 줄을 준다.
- 원본 정답은 읽기만. 정답이 있는 항목을 열면 정답 박스가 **편집 가능한 라벨**로 뜨고(src gt), 고친 프레임만 손라벨 저장소에 남는다. 이미지는 `image_labels.json`(클립 이름 `img:<상대경로>`).
- `use: eval`(채점 전용)에서 만든 라벨 행은 `eval: true` 가 붙어 학습셋 빌더가 뺀다. `use: none` 은 라이선스(LLVIP·FLIR) 등으로 학습 금지.
- 학습셋 빌더 `scripts/build_trainset.py fire|person`: 손라벨 > SAM 전파 > 원본 정답(어댑터) 순으로 합쳐 `trainset_<mode>_<날짜>/` 를 만든다. 영상은 라벨된 시각 프레임을 뽑고, 이미지는 심링크. 검증은 클립/파일 해시로 분리.

## 라벨 저장소 셋 (표시·학습 우선순위 순)

| 저장소 | 파일 | 만드는 곳 | 뜻 |
|---|---|---|---|
| 손라벨 | `data/학습데이터/손라벨/{person,fire}_labels.json` | 편집기 저장(탭·드래그·검수 수정) | 학습 데이터. `cls -1` 행 = 검토완료(박스 없음) 마커 |
| SAM 전파 | `data/학습데이터/자동라벨/sam2/<stem>.json` | 전파 큐 워커 | `frames{t:{obj:[x,y,w,h]}}` · `polys{t:{obj:윤곽선}}` · `seeds`. 바로 학습에 쓴다 |
| DINO | `data/학습데이터/자동라벨/dino/<stem>.json` | 배치 스크립트 | 사람 클립의 첫 등장 프레임 찾기, 기록 없는 프레임의 초안. 학습엔 안 들어간다 |
| 정답 | `data/학습데이터/정답라벨/<stem>.json` | 가져오기 스크립트 | 데이터셋 제공 정답(박스·점). 읽기 전용, 참조샷 재료 |

규칙
- 손라벨 박스가 있는 프레임은 SAM 저장소에서 빠진다. `savelabel` 이 그 프레임을 빼고, 전파 저장(`sam2_store_write`)이 건너뛴다.
- 검토완료 마커(`cls -1`)는 DINO·정답 초안만 막는다. SAM 전파 결과는 그 위에 보인다.
- 프레임 격자: 사람 0.5초(2FPS), 화재 1초. 저장소 키는 `"190.5"` 꼴(`tkey`).

## 화재 객체 규약 (한 곳: editor.js `FIRE`)

객체 1 = 불(cls 0), 객체 2 = 연기(cls 1). 숫자키 1/2 로 고르고, 탭 = SAM 점, 드래그 = 그 객체의 박스(참조샷). 사람 클립은 객체 = 사람 번호, cls 0.

## 편집기 조작 → 서버

| 조작 | 클라이언트 | 서버 |
|---|---|---|
| 탭(점)·박스 프롬프트 | `samPoint` → `applyMask` | `POST /api/sam2_mask` (SAM2 이미지 모델, 코어) |
| 저장 | `saveNow` → `postLabel` | `POST /api/savelabel` (손라벨 갱신 + 같은 프레임 SAM 제거) |
| 전파 | `bGo` → 참조샷(박스+점)·구간 a/b·방식 | `POST /api/sam2_propagate_start` → 큐 → `sam2_propagate_objs` → `sam2_store_write` |
| 이어서 전파(교정) | 전파 결과가 있는 클립에서 참조샷을 더 찍으면 `refineWindow` 가 [직전 참조, 직후 참조] 구간만 보낸다 | 같은 엔드포인트, a/b 로 구간 제한, 객체 단위 병합 |
| 전파 지우기 | `bClr` | `POST /api/sam2_clear` |
| 검수 격자 | `openAutoReview`(SAM 결과만) / `openShot`(확대·수정) | `sam2_drop` · `savelabel` |
| DINO+SAM 감지(화재) | `bFuse` | `POST /api/fuse_detect` (Grounding DINO 박스 → SAM 마스크) |
| 진행 표시 | `watchJob`(편집기) · `pollJobs`(헤더) | `GET /api/sam2_jobs?clip=` |

## 전파 방식 (`PROP_DEFAULT_MODE`, `/api/config`)

- `separate`(기본): 객체마다 독립 세션·독립 임계(`PROP_THR`). 불·연기가 한 마스크로 뭉개지지 않는다.
- `joint`: 모든 객체를 한 세션에(비교 실험용).
- `detect`: 프레임마다 DINO 박스 → SAM 마스크(시간 기억 없음, 비교 실험용).
- 비교 스크립트 `_kisa_port/eval_prop_modes.py` → `_kisa_port/eval_prop_modes_<시각>.md`.
- 2026-09-10 비교(화재 8클립, 첫 손라벨 프레임만 참조 → 이후 손라벨 프레임과 IoU): separate 불 0.583 · 연기 0.084 · 불 잡음 94% · 연기 잡음 39%. joint 는 separate 와 같은 수치(transformers SAM2 비디오는 객체 간 argmax 억제를 하지 않아 차이가 없다). detect 는 불 0.566 · 연기 0.067 에 흔들림 2배, 시간 2배. 연기 임계 -0.5 는 차이 없음. → 기본값 separate 유지. 연기는 어느 방식도 첫 참조 한 장으로는 7초 뒤를 못 따라가므로 참조샷을 자주 찍고 이어서 전파로 교정하는 흐름이 맞다.

구간은 참조샷 사이 세그먼트 단위로 새 세션을 만든다(transformers SAM2 비디오가 시작 프레임 뒤의 조건 입력을 쓰지 않아서).

## 상태(클라이언트)

- `LB` 화면 상태(mode·clip·sec·boxes·src). `src` 는 hand/sam/gt/dino/none.
- `samState(clip)` = `SM` (참조샷 seeds·objs·cur·구간 a/b·propFrames). 브라우저 localStorage 에 남는다.
- 캐시: `SAMMAP`/`SAMPOLY`/`SAMSEEDS`(전파 저장소), `DINOMAP`, `GTMAP`, `SAMFR`(목록 배지). 무효화는 `samInvalidate`/`samForget` 만 쓴다.
- 되돌리기: `_HIST[clip]` 하나. 다른 프레임 항목은 `_PENDING`(10초 유효)으로 이동 후 적용.

## 운영 주의

- 서버 재시작은 진행 중 전파가 없을 때(`/api/sam2_jobs`). 큐는 메모리에 있다.
- 재시작 명령은 kill 과 start 를 다른 ssh 호출로(pkill -f 가 자기 명령줄을 죽인다).
