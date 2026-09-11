# 데이터 활용 대장 (Claude 참조 전용)

> 새 데이터를 들여올 때/부적합 판정할 때 이 파일을 읽고 갱신한다. 2026-09-11 기준. 규격의 원본은 `configs/datasets.yaml`(카테고리별 mode·media·gt·classes·use) 이고 이 문서는 사람용 요약이다.

## 원본데이터 (data/원본데이터/)

### 방화(화재/연기)
| 원본데이터 | 내용 | 라벨 | 학습 연결 |
|---|---|---|---|
| kisa_연구개발_방화영상 | 방화 영상 75편(xml GT) | 손라벨 `손라벨/fire_labels.json` 229프레임 | → `human_fire` 1,140장(±2초 전파), 큐에서 ×5 |
| kisa_산불_원천 | 합성 산불 영상 516편 + 이미지 9,500 | 손라벨 대상 | (손라벨 편집기 대상) |
| aihub71751_48k | AI-Hub 71751 화재 12프레임 평면풀 **39,003장** | YOLO 0불/1연기 | **큐 베이스**. 격프레임 절반 → `아래 aihub71751_24k` |
| aihub71330_산불 | `frames/`=양성 7폴더 **59,474장**(화염 11,007·연기 52,925 이미지) · `안개구름/`=음성 | 100% 짝, 화염 11,717·연기 71,788 박스. 굴뚝연기는 실제 연기라 `PositiveRealDB_굴뚝연기`로 개명(2026-09-09) | 양성 → `wildfire_pos_yolo` 59,474 · 음성 → `wildfire_fog_neg` 12,007 |
| open_fasdd | FASDD train 63,546 · val 15,884 · test 15,884 (COCO json, 0 fire/1 smoke) | 파일명 중복 0 → 전부 학습 | → `fasdd_yolo` **95,314** · 증강본 `fasdd_snowfog`/`fasdd_snow2` |
| open_dfire | D-Fire 21,527(train+val+test) | 원본 0 smoke/1 fire → **스왑**해 0불/1연기 | → `dfire_yolo` 21,527 |
| open_azimjaan_fire | Roboflow 3클래스 **0=구름 / 1=불 / 2=연기**(data.yaml 없음, 라벨 증거로 확정) | 대시보드는 원본 그대로(구름에 박스 보임) | → `azimjaan_yolo` **10,739**: 불→0·연기→1·구름 박스 제거 후 구름 이미지 2,000 서브샘플=하드네거 |

### 사람(침입/배회/쓰러짐)
| 원본데이터 | 내용 | 라벨 | 학습 연결 |
|---|---|---|---|
| kisa_연구개발_사람영상 | 사람 이벤트 영상 825편(xml Alarm/StartTime) | 의사라벨(person_v3 티처) 프리필 → 손라벨 `손라벨/person_labels.json`(0.5초=2FPS) | 미연결(person 학습 재구축 시) |
| aihub_침입쓰러짐영상 | 침입/쓰러짐 80편, json `event_frame` GT | 같은 방식 손라벨(현재 78박스) | 미연결 |
| open_llvip | LLVIP visible 15,488 + infrared 15,488, person VOC | 비상업 라이선스 → `use: none`(학습 금지) | 진단용만 |
| open_coco | COCO 2017 train 118,287장(`coco/images/train2017` · 라벨 `coco/labels/train2017`, ultralytics 변환) | `classes: {0: 0}` person 만, 나머지 79클래스 drop. CC-BY 4.0 | `use: train`(사람). 대시보드에서 편집 가능(2026-09-11 재도입) |

### 채점 (학습 절대 금지)
| 원본데이터 | 내용 |
|---|---|
| kisa_배포_검증영상 | KISA 채점셋 4항목(방화10·침입30·배회30·쓰러짐10) + zone_maps. **`use: eval`**: 학습·하드네거티브 어디에도 안 들어간다(빌더가 카테고리로 막고 마지막에 '채점 클립 0건' 단언). 여기 친 손라벨·전파 결과는 **mAP 검증셋**(`evalset_fire`/`evalset_person`)으로만 쓴다. 방화 F1 채점 = `deploy_val/방화(10개)/배포` |

## 학습데이터 (data/학습데이터/) 현역 세트
| 세트 | 장수 | 출처/비고 |
|---|---|---|
| fasdd_yolo | 95,314 | open_fasdd 3split 전부 |
| fasdd_snowfog / fasdd_snow2 | 3,930 / 702 | fasdd 설경·안개 증강(train 기반, val/test 증강은 미생성) |
| dfire_yolo | 21,527 | open_dfire 클래스 스왑 |
| azimjaan_yolo | 10,739 | 양성 8,739 + 구름 하드네거 2,000 |
| wildfire_pos_yolo | 59,474 | aihub71330_산불 frames/ 양성 |
| wildfire_fog_neg | 12,007 | aihub71330_산불 안개구름/ 음성 |
| human_fire | 1,140 | fire_labels.json → `build_humanset.py` (러너가 자동 재빌드) |
| aihub71751_24k | 19,502 | 48k 격프레임 절반. 24k vs 48k 비교 프록시 |
| 손라벨/ | - | `fire_labels.json` · `person_labels.json` · `image_labels.json`(이미지, 키 `img:<상대경로>`). 행 = 프레임 박스(`obj` = 객체 번호), `cls:-1` = 검토완료(배경) 마커, `eval:true` = 채점 클립 행 |
| 자동라벨/sam2/ | - | 클립별 SAM 전파 결과 `<stem>.json` {frames, polys, seeds}. 손라벨 프레임은 여기서 빠진다 |
| 정답라벨/ | - | 원본 정답(XML/JSON)의 복사본. 원본은 읽기만(`write_json` 이 RAW 아래 쓰기를 거부) |
| evalset_fire · evalset_person | 771 · 1,289 프레임 | `build_evalset.py`: 채점 클립 손라벨·전파 + 발생 전 배경 표본. 검증 전용, 러너가 채점 때마다 재빌드 |

## 부적합·삭제 (재다운로드 금지)
- **aihub71953_다각도CCTV**(483.7G, 미보유·받지 말 것): 라벨에 박스는 있다(`obj_bbox`·`frame_id`·`obj_id`·`obj_label`, 2시점 c1·c2). 그러나 **한 영상에 객체 1명만 추적**한다(`obj_id` 가 사실상 단일). KISA 규칙의 핵심이 다수면 마지막 사람이라 다중 객체 GT 가 없으면 규칙 검증에 못 쓴다. 게다가 라벨은 영상당 3프레임 샘플이라 학습용으로도 양이 적다. → **활용 불가**. ⚠이력: 박스 없음으로 오판해 166G 삭제 → 박스 확인 후 22G 재다운로드 → 단일객체 추적 확인으로 다시 삭제(2026-09-10).
- ~~open_coco~~ → 2026-09-11 재도입(person 만, 위 사람 표). 의사라벨·합성 세트(person_v2/v3/v4·person_pl·pose_v2·aihub_int_pl·human_synth·person_pose, 8.3GB)는 2026-09-11 삭제: 의사라벨을 학습에 쓰지 않기로 결정.
- **open_cctv_fire**(355M, 2026-09-09 삭제): 분류 라벨만, 박스 없음.

## 규칙
- 외부 데이터의 train/val/test 는 **같은 클립·중복 파일이 아니면 전부 학습**에 합친다(평가는 KISA 채점셋).
- 음성(배경) 이미지는 전체 학습셋의 **10% 이내**(넘으면 리콜 붕괴). 큐 mix 마다 비율 확인.
- 사람/이벤트 데이터는 **프레임 박스 또는 이벤트 시각 GT** 가 있어야 유효. 받기 전에 GT 구조부터 확인.
- 클래스 규약: **0=fire(불), 1=smoke(연기)**. 외부셋은 반드시 매핑 확인(D-Fire 스왑, azimjaan 3클래스 사례).

## 우리가 만든 라벨 → 학습 (2026-09-11)
- 빌더 `scripts/build_trainset.py fire|person [--neg 5]` 하나가 전부 합친다. 우선순위 **손라벨 > SAM 전파 > 원본 정답(어댑터)**. 같은 프레임에 손라벨이 있으면 전파는 무시.
- 영상 라벨(손·전파)은 그 시각 프레임을 mp4 에서 뽑아 jpg 로, 이미지는 원본을 심링크(복사·수정 없음).
- 원본에 박스가 있는 이미지(dfire·fasdd·azimjaan·coco 등)는 대시보드에서 정답이 편집 가능한 라벨로 뜨고, 고친 것만 `image_labels.json` 에 남는다. 빌더는 그 이미지에 손라벨이 있으면 손라벨을, 없으면 원본 정답을 쓴다.
- 하드 네거티브: 손라벨 클립에만, 라벨 구간 앞뒤 배경 프레임을 빈 라벨로. 사람은 바로 앞뒤, 불연기는 10프레임 버퍼. 클립당 앞/뒤 각 5장, 상한 = 그 클립 손라벨 양성 수. 원천 데이터셋의 네거티브(wildfire_fog_neg 등)는 그대로 쓴다.
- 채점 클립(`use: eval`)은 라벨이 있어도 학습·배경 어디에도 안 들어간다. 빌더 끝에 단언(2026-09-11 dry-run: 233,702항목 중 채점 클립 0건).
- mAP: `scripts/eval_map.py fire --exp <실험>` 이 `evalset_<mode>/data.yaml` 로 best.pt 를 검증해 `results/<exp>/eval_map.json`. 러너가 채점 뒤 자동 실행, 결과 탭 `mAP(채점셋)` 열. 에폭 검증도 `defaults.val_set` 으로 이 셋을 쓴다(학습 목록에서 뽑던 600장은 누수였다: mAP50 0.87 → 채점셋 0.22~0.31).
