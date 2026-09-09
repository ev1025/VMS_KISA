# vms 레포 규약 (KISA 지능형 CCTV: 방화/침입/배회/쓰러짐)

vms/ 자체가 레포지토리다. 심링크·중복 폴더 금지(general_yolo/yolo_fire_smoke 폐기됨).

## ★ 데이터 배치 규칙 (새 데이터 받으면 반드시 이대로)
`data/` 직속에는 **원본데이터 / 학습데이터 딱 둘만** 둔다. 그 외 중간 폴더 금지.

### data/원본데이터/  = 받은 원본 그대로
- 소스별 한 폴더. annotation(xml/json)이 딸려오면 원본과 함께 둔다.
- 명명 = `<출처>_<내용>` , 출처 접두는 **kisa_ / aihub<번호>_ / open_**
  - 예: `aihub71330_산불_안개구름`, `aihub71751_화재발생예측_라벨`, `kisa_배포_검증영상`,
        `kisa_연구개발_방화영상`, `kisa_산불_원천`, `open_fasdd_flir_llvip`, `open_coco`
- 다운로드 목적지도 여기(임시 dl 폴더는 그 안에). AI허브=aihubshell, 키는 ~/.aihub_key

### data/학습데이터/ = 학습에 쓰는 가공셋 (YOLO 포맷)
- 구조: `images/train`, `labels/train`, `data.yaml` (val은 24k val 공유 등)
- 원본에서 파생/합성/의사라벨/하드네거티브 등 "학습에 들어가는 형태"만.
- **원본 이미지 재복제 금지** → 원본데이터를 심링크로 참조
  (예: `fasdd_yolo/images/*` → `data/원본데이터/open_fasdd_flir_llvip/fasdd/images/*` 심링크)
- 예: dataset_24k, fasdd_yolo, fasdd_snow2/snowfog, human_fire(손라벨), wildfire_fog_neg(음성), person_v3 등

### 절대 하지 말 것
- data/ 밑에 fire/person/deploy/external 같은 중간 그룹 폴더(전부 원본/학습으로 흡수)
- 채점셋(배포/검증)에 학습 라벨 달기 = train/test 유출

## 그 외 폴더
- **model/** : 모든 가중치. `pretrained/`(yolo11*, yolov8, yolo26n, clip 등 베이스), `sr/`(RealESRGAN), 루트=프로젝트 학습 .pt(fire_base, person_v2/v3, run_*)
- **labels/** : 손라벨. `fire_labels.json`(원천 라벨), `full/`(프레임), `new/`(하드프레임)
- **runs/** : 학습 산출. `kisa/`, `par/`(human_full 등), `fall_track/`. `_archive/`=옛 실험
- **results/** : 점수/리포트(json·txt), `par/tl/`(신호 타임라인), `_archive/`
- **dumps/** : 추론 트랙 덤프 — 대시보드 사용: `intrusion_tile`(침입) `loiter_trk_id`(배회) `fire_box`(방화). `_archive/`=옛 변형
- **dash_v2/** : 통합 대시보드(serve_kisa.py:8890, app.js, build_*_meta.py). 데이터확인·영상검수·라벨생성
- **scripts/ configs/ feats/ data_prep/** : 스크립트·튜닝설정·캐시피처·전처리

## 대시보드 통합 로직(재사용)
- 영상 = `renderCenter(row)` 하나로(영상검수·데이터확인 원본영상 공용, raw는 signal_type:"raw"+sa:null)
- 이미지 = 중앙 img + SVG 박스 오버레이(라벨생성·데이터확인 공용, 세로중앙 margin:auto)
- 우측 정보 = rtitle + KV 카드, 리스트 왼쪽 = 태그 배지

## 데이터 (docs/data.md 참조)
새 데이터를 들여오기 전·후 반드시 **`docs/data.md`** 를 읽고 갱신한다.
- 거기에 데이터별 **활용 여부·이유**, 부적합/삭제 목록, GT 유무 판별 기준이 있다.
- 새 데이터는 **GT 구조부터 확인**(프레임 박스·이벤트 프레임/시각이 있나) → 활용가능/불가 + 이유를 data.md에 기록.
- docs/ = Claude가 참조하는 md 전용 폴더.
