# vms 레포 규약 (KISA 지능형 CCTV: 방화/침입/배회/쓰러짐)

vms/ 자체가 레포지토리다. 심링크·중복 폴더 금지(general_yolo/yolo_fire_smoke 폐기됨).

## ★ 데이터 배치 규칙 (새 데이터 받으면 반드시 이대로)
`data/` 직속에는 **원본데이터 / 학습데이터 딱 둘만** 둔다. 그 외 중간 폴더 금지.

### data/원본데이터/  = 받은 원본 그대로
- 소스별 한 폴더. annotation(xml/json)이 딸려오면 원본과 함께 둔다.
- 명명 = `<출처>_<내용>` , 출처 접두는 **kisa_ / aihub<번호>_ / open_**
  - 예: `aihub71330_산불`(frames/=양성, 안개구름/=음성), `aihub71751_48k`(12프레임 평면풀), `kisa_배포_검증영상`,
        `kisa_연구개발_방화영상`, `kisa_산불_원천`, `open_fasdd`, `open_llvip`, `open_dfire`, `open_azimjaan_fire`
- 다운로드 목적지도 여기(임시 dl 폴더는 그 안에). AI허브=aihubshell, 키는 ~/.aihub_key

### data/학습데이터/ = 학습에 쓰는 가공셋 (YOLO 포맷)
- 구조: `images/train`, `labels/train` (val 은 큐 러너가 목록으로 600장 self-val 을 만든다. 세트 안에 val 두지 않음)
- 원본에서 파생/합성/의사라벨/하드네거티브 등 "학습에 들어가는 형태"만.
- **원본 이미지 재복제 금지** → 원본데이터를 심링크로 참조
  (예: `fasdd_yolo/images/train/*` → `data/원본데이터/open_fasdd/images/{train,val,test}/*` 심링크)
- 예: fasdd_yolo(95,314=train+val+test), dfire_yolo, azimjaan_yolo(리매핑), wildfire_pos_yolo(산불 양성), wildfire_fog_neg(음성),
  human_fire(손라벨→build_humanset.py 산출), aihub71751_24k(48k 격프레임 절반=24k 프록시), person_v3 등
- **외부 데이터의 train/val/test 는 같은 클립이 아니면 전부 학습에 합친다**(우리 평가는 KISA 채점셋이므로)

### data/학습데이터/손라벨/ = 손라벨 원천(JSON, 편집기가 쓴다)
- `fire_labels.json`(방화, 초 단위) · `person_labels.json`(사람, 0.5초=2FPS). 좌표 x,y 는 **좌상단**·정규화
- `cls: -1` 행 = "검토했고 객체 없음" 마커(박스 아님). 학습셋 빌더는 반드시 건너뛴다
- 학습 반영은 `scripts/build_humanset.py`(원자적 덮어쓰기, rm 안 함). `exp_queue.py --rebuild-human` 이 실험 전에 자동 실행

### 절대 하지 말 것
- data/ 밑에 fire/person/deploy/external 같은 중간 그룹 폴더(전부 원본/학습으로 흡수)
- 채점셋(배포/검증)에 학습 라벨 달기 = train/test 유출

## 실험 실행 (유일 진입점 = scripts/exp_queue.py)
- `python scripts/exp_queue.py run configs/<queue>.yaml --jobs 3 [--wait-tmux <세션>] [--rebuild-human]` · `status` 로 진행 확인
- 실험 추가 = yaml 에 한 항목. **실행 중인 .sh 를 편집해 실험을 붙이지 않는다**(바이트 오프셋 깨짐·고아 프로세스 원인)
- 러너가 `docs/EXPERIMENTS.md §0` 규약을 강제: train.txt 목록(심링크 폴더 X) · val_small 600 · `multi_scale=0.5` · `--cache ram --workers 8`
  · 오버샘플=목록 반복 · 잡별 000.jpg 로 labels.cache 분리 · 동시 잡 N + VRAM 게이트
- 산출: `runs/<exp>/<model>/weights/best.pt` · `results/<exp>/{meta.json,score.txt}`(item 필드로 4항목 구분) · `logs/queue/<exp>.log`
- 재실행 안전: best.pt 있으면 학습 생략, score.txt 있으면 전체 생략. `_exp/` 는 잡별 임시 목록·캐시(지워도 됨)

## 그 외 폴더
- **model/** : 모든 가중치. `pretrained/`(yolo11*, yolov8, yolo26n, clip 등 베이스), `sr/`(RealESRGAN), 루트=프로젝트 학습 .pt(fire_base, person_v2/v3, run_*)
- **configs/** : 실험 큐 yaml(`queue_fire_20260909.yaml` 등)
- **runs/** : 학습 산출. 신: `runs/<exp>/<model>/` · 구: `runs/<이름>/`, `kisa/`, `par/`, `fall_track/`, `_archive/`
- **results/** : 신: `results/<exp>/{meta.json,score.txt}` · 구: 평면 `<이름>.txt`(방화), `intrusion.txt`(침입). 대시보드 결과탭이 둘 다 읽음
- **dumps/** : 추론 트랙 덤프 — 대시보드 사용: `intrusion_tile`(침입) `loiter_trk_id`(배회) `fire_box`(방화). `_archive/`=옛 변형
- **dash_v2/** : 통합 대시보드(serve_kisa.py:8890). JS 는 `js/{core,review,data,editor,main}.js`(app.js 는 스텁). 데이터확인·영상검수·결과
- **scripts/** : 현역 스크립트만. 죽은 경로 참조·대체된 것은 `scripts/_archive/<날짜>/`(README 에 사유). **logs/** 도 동일하게 `_archive/`

## 대시보드 통합 로직(재사용)
- 영상 = `renderCenter(row)` 하나로(영상검수·데이터확인 원본영상 공용, raw는 signal_type:"raw"+sa:null)
- 이미지 = 중앙 img + SVG 박스 오버레이(라벨생성·데이터확인 공용, 세로중앙 margin:auto)
- 우측 정보 = rtitle + KV 카드, 리스트 왼쪽 = 태그 배지

## docs (읽고 갱신)
- 새 데이터 들여오기 전 → `docs/data.md`
- 실험 큐 돌리기 전 → `docs/EXPERIMENTS.md`
