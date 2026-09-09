# 실험 방법론·이력 (KISA 4항목: 방화·침입·배회·쓰러짐)

이 문서는 **실험 큐를 돌리기 직전에만** 읽는다. 평소 작업에는 필요 없다.
목적은 두 가지. ① 어떤 축으로 실험할 수 있는지(방법론) ② 그 축에서 이미 무엇을 돌려 어떤 결과가 났는지(이력).
같은 실험을 두 번 돌리지 않기 위한 문서다.

갱신 2026-09-09 · 근거 = `results/ALL_RESULTS.md`, `results/par/*`, `results/_archive/*`, `NIGHT_SUMMARY.txt`, `scripts/*`

---

## 0. 실행 인프라 규약 (안 지키면 느려지거나 죽는다)

| 항목 | 값 | 이유 |
|---|---|---|
| GPU | B200 1장 (183GB) | `CUDA_VISIBLE_DEVICES=0` |
| 동시 잡 | **3개** (`par_fire.sh` MAXJ=3) | 72코어인데 CPU 가 병목(PSI 95%). 4잡이면 코어당 3~4배 느려짐 |
| VRAM 게이트 | 120GB 초과면 다음 잡 대기 | 잡 시작 시차 90초 |
| 데이터 지정 | **`train.txt` 이미지 목록** (심링크 폴더 아님) | Lustre 소파일 심링크가 37개/s 로 막힘. 목록 방식은 즉시 |
| 오버샘플 | train.txt 에 **같은 경로를 여러 번** 씀 | ultralytics 는 목록 중복을 제거하지 않음 |
| 캐시 | `--cache ram --workers 8` | Lustre 소파일 I/O 회피 |
| val | `_par/val_small.txt` 600장 | 전체 val 은 에폭당 NMS 3분, 600장은 25초 |
| labels.cache 충돌 | 잡별 전용 폴더에 파일 1개(`000.jpg`)를 두고 그걸 목록 맨 앞에 | 캐시 경로가 잡마다 분리됨 |
| multi-scale | `--multi-scale --extra multi_scale=0.5` | ultralytics 8.4 에서 `True` 는 0~1280px 범위라 VRAM 120GB 먹음. 0.5 면 320~960 |
| 학습 진입점 | `python model.py train --models <m> --data <yaml> --imgsz <n> --batch <n> --epochs <n>` | `model.py` 가 유일한 학습 CLI |
| 채점 진입점 | `python score_kisa.py <best.pt> --videos <dir> --gt <dir> --stride 0.5 --imgsz <n> [--tiles]` | 규칙 스윕까지 이 안에서 |

---

## 1. 실험 축 (방법론) 과 이미 돌린 값

### A. 입력 해상도 (imgsz)

- 구현: `model.py train --imgsz`, 채점도 같은 값으로 `score_kisa.py --imgsz`
- 돌린 값: **640**(기본) · **960** · **1280**
- 이력: `fire_s960_20260908`(yolo11s@960), `fire_s1280_20260908`(yolo11s@1280, batch 64), `fire_m960_20260908`(yolo11m@960+fasdd), `human960`, `hard_fa960`, `fa_*_960` 계열
- 결과: 960 이 640 을 확실히 이기지 못했다. `hard_fa960` 66.67 vs `hard_fa` 유사, `human960` 은 결과 미기록
- 주의: **학습 imgsz 와 채점 imgsz 를 반드시 같게** 둔다. 다르면 소형 불꽃 리콜이 무너진다

### B. 모델 백본

- 레지스트리: `model.py` 의 `MODELS` = yolov8n/8s, yolov5nu/5su/5mu · `BASELINE` = yolov8m
- 실제로 많이 쓴 것: **yolo11s**(기본), yolo11m, yolov8m
- 별도 계열: `scripts/rtdetr_train.py`(RT-DETR), `scripts/world_smoke.py`(YOLO-World 교사, 미탐 프레임 스모크 테스트), yolo26n(pretrained 보유)
- 이력·결과: `FIRE_RTDETR_SCORES` F1 70.59(구 규칙). yolo11s 가 속도·성적 균형에서 기본값으로 굳음
- 안 해본 것: yolo11n/11l/11x 비교, yolov8x, imgsz 축과의 교차(11n@1280 등)

### C. 데이터 조합 (추가 학습셋)

베이스는 항상 `dataset_24k`(방화 원천 24k). 여기에 아래를 더한다.

| 추가셋 | 내용 | 쓴 실험 |
|---|---|---|
| `human_fire` | 손라벨 방화 프레임 (현재 1,045장) | 전부. 배수는 축 D |
| `human_synth` | 손라벨 불 패치를 정상 배경에 합성 (299장) | `synth_mix` |
| `fasdd_yolo` | FASDD 오픈 화재 63,546장 | `fa_*`, `fire_m960`, `fire_fasdd` |
| `fasdd_snow2` / `fasdd_snowfog` | FASDD 설경·안개 3,930장 | `snow_x10/x30`, `fire_snow*`, `fire_fogsnow` |
| `wildfire_fog_neg` | AI허브 71330 구름·안개 negative 11,924장 | `fog_x1/x3`, `fire_fog1`, `fire_fogsnow` |
| `_hard/*.txt` | 하드네거티브 목록 9종 (beach_sand·white_smoke·haze24k·fasdd_neg·snow_fasdd 등) | `hard_mix`, `hard_fa` |

- 결과 요지: FASDD·설경·안개를 넣어도 **배포 채점 F1 은 안 올랐다**(`fire_fasdd`, `fire_snow*`, `snow_x10` 50~66). 도메인이 달라서 mAP 만 오르고 실제 판정은 그대로
- `human_only`(손라벨만 학습): **mAP50 0.0111, F1 33.33 로 붕괴**. 1,045장으로는 학습 불가. 24k 베이스는 필수

### D. 오버샘플 배수

- 구현: `train.txt` 에 같은 목록을 k번 반복 (`par_fire.sh` 의 `mkds <이름> <배수> <합성포함>`)
- 돌린 값: human_fire **×1, ×3(ov3), ×5(mix_human_full), ×10(ov10), ×20(ov20)** · 설경 ×10/×30 · 안개 ×1/×3
- 결과: **×5 와 ×10 이 최고(F1 88.89)**, ×3·×20 은 77.78 로 떨어짐. 배수는 중간이 최적
- 학습 장수: ov3 22,975 · ov10 30,290 · ov20 40,740 · snow_x10 35,733 · fog_x3 60,837

### E. 24k 비율 스윕 (베이스 데이터 양)

- 구현: `scripts/fire_matrix2.py ratio`
- 돌린 값: 0% / 10% / 25% / 50% / 100%
- 결과: `0% → F1 30.77` · `10% → 53.33` · `25% → 66.67` · `50% → 66.67` · `100% → 66.67`
- 해석: **25% 에서 포화**. 24k 를 더 넣어도 배포 성적은 안 오른다. 프레임 중복(30fps 360프레임/클립) 때문

### F. 의사라벨 (pseudo-label)

- 구현: `scripts/pl_*.py` (fire75 · ai_fire · ir_fire · person · person_track · pose)
- 방식: 교사 모델(x급) → 타일 추론(`infer_tiled`) → NMS → `keep-conf 0.35` 이상만 박스 채택. `empty-conf 0.15`~0.35 구간이 걸린 프레임은 **버림**(미탐이 negative 로 굳는 것 방지)
- 샘플링: `--sample-s 5`(5초 간격), `--cap 30`(영상당 최대 30장)
- 산출: `fire75_pl`, `ai_fire_pl`, `ir_fire_pl`, `night_track_pl`, `person_pl`, `aihub_int_pl`(AI허브 71850 침입 867장)
- 한계: 교사 지식의 복사다. 새 정보가 없고 오탐도 정답으로 굳는다. **평가에 쓰면 안 된다**

### G. 하드네거티브

- 구현: `scripts/build_hardsets.py` → `data/학습데이터/_hard/*.txt` 목록
- 종류: `beach_sand`(모래·노을), `white_smoke`, `haze24k`, `fasdd_neg`, `fasdd_smallfire`, `snow_fasdd`, `fasdd_smoke`, `fasdd_fire`, `fasdd_all`
- 이력: `hard_mix`(35,001장), `hard_fa`, `hard_fa960`
- 결과: `hard_fa960` 66.67 (정검 6 미검 4 오검 2). 오검을 줄이는 대신 미검이 늘어나는 교환이 반복됨

### H. 크롭 학습

- 구현: `scripts/make_crops.py` → `labels/crop`
- 방식: 발화점 후보를 **깜빡임(temporal std)** 으로 찾는다. 연속 24프레임(3프레임 간격)의 표준편차가 크고 기준보다 밝은 영역을 512px 크롭
- 근거: 불은 시시각각 흔들리고, 주차된 차·건물 조명은 안 흔들린다
- 용도: 손라벨 작업용 크롭 생성이 주였다. **크롭 이미지로 학습한 실험은 아직 없다** (미개척 축)

### I. 추론 타일 (inference tiling)

- 구현: `score_kisa.py --tiles`, `scripts/fire_tilescan.py`, `scripts/person_tilescan.py`
- 방식: 프레임을 **3x3 으로 쪼개 각각 960 으로 추론** 후 좌표 합성
- 결과: 침입에서 결정적이었다. **ByteTrack 기존 덤프 77.55 → 타일 덤프 + 자체 트래커 92.86**
- 배회는 반대. 타일 86.21 < 기존 86.21 미만, ByteTrack 기존 덤프가 **93.10** 로 더 좋았다
- 비용: 프레임당 9회 추론. 스트라이드 0.5초로 채점

### J. 초해상 (Super Resolution)

- 구현: `scripts/sr_test.py`, `scripts/sr_fp.py` (Real-ESRGAN ×2 → 1280 추론), 가중치 `model/sr/`
- 결과(약신호 10편): 규칙 충족 영상 **base 5/10 → SR 6/10**. 1편(`C00_012_0007`)만 conf 0.16 → 0.85 로 살아남
- 오탐 검증(`sr_fp.py`): **base F1 66.7 → SR 57.1 로 하락**(정상 영상에서 오탐 1건 발생)
- 결론: 리콜 1편 얻고 오탐 1건 얻는 교환. **채택 안 함**

### K. 도메인 적응 (FDA)

- 구현: `scripts/fda_build.py`, `fda_preview.py`, `fda_x_train.sh`
- 방식: 소스 이미지의 저주파 스펙트럼을 타깃 도메인으로 치환(Fourier Domain Adaptation)
- 결과: `FIRE_FDA_SCORES` F1 40.00 (정검 3 미검 7 오검 2). **실패**

### L. 시퀀스·트랙 판정 (방화 외 3항목)

| 접근 | 구현 | 결과 |
|---|---|---|
| 프레임 독립 판정 | `score_kisa.py` 규칙 | 방화 88.89 |
| 트랙별 독립 판정 | `scripts/fall_track.py` | 쓰러짐 **88.89** (th0.0 need1) |
| 시퀀스 분류기 | `fall_seq_train.py`, `fall_seq_v2.py`, `seq_train.py` | 쓰러짐 84.21 / v2 29.60 |
| 골격 시공간 그래프 | `posec3d_train.py`, `posec3d_v2/v3.py` | 43.00. **실패** |
| 트래커 선택 | ByteTrack(기존 덤프) vs 자체 트래커(타일 덤프) | 침입은 자체, 배회는 ByteTrack |

### M. 판정 규칙 그리드 (학습과 무관, 후처리)

- 방화: `f<conf> <n>/<m>` = conf 임계 + m프레임 중 n프레임 충족. 연기 가중치 `+0.2`
  - 최고: `f0.50 5/12 연기+0.2`(human_full) · `f0.10 3/6 불만`(ov10) 둘 다 88.89
- 침입: `conf 0.375 3/4 hold2 settle24s` + **마지막 사람 규칙** → 92.86
- 배회: `conf0.4 need0 D6s delay10s settle5s gap6` + **마지막 배회자 규칙** → 93.10
- 쓰러짐: `th0.0 need1` 트랙별 → 88.89
- **핵심 교훈**: KISA 스펙의 "다수면 마지막 사람" 정의를 트랙 ID 규칙으로 구현한 것이 침입 +15, 배회 +22 를 만들었다. 모델 교체보다 규칙이 컸다

### N. 하이퍼파라미터 최적화

- 구현: `model.py tune --model <m> --imgsz <n>` (Optuna, proxy 학습)
- 산출: `configs/tune_best_yolov8{n,s,m}.yaml` (lr0 0.000886 · SGD · box 10.26 · cls 0.78 · mosaic 0.91 · mixup 0.20 등)
- 도메인 기본 레시피(`model.py` `RECIPE`): `flipud=0`(불꽃 상하반전 금지) · `fliplr=0.5` · `hsv_s=0.5, hsv_v=0.4`(색왜곡 약하게) · `mosaic=1.0, close_mosaic=10` · `cos_lr=True` · `patience=30`
- 재학습 이식: `model.py train --hp configs/tune_best_yolov8s.yaml`
- 안 해본 것: yolo11s 전용 HPO (기존 yaml 은 v8 계열 기준)

### O. 교차검증·홀드아웃

| 방식 | 구현 | 결과 |
|---|---|---|
| FASDD 5-fold | `scripts/fasdd_kfold.py` | **5 fold 전부 학습 실패**(75,901장 규모에서 죽음). 재시도 필요 |
| 방화 k-fold | `scripts/fire_kfold.py human mix24k` | `results/par/FIRE_KFOLD.txt` |
| 장소 홀드아웃(LOO) | `scripts/fire_matrix2.py loo` | 장소 8종(FWW·GAH·MS·OLMF·RE·VTSP…) 중 GAH 50.00 · MS 58.82, 나머지 결과 비어 있음(미완) |
| LOOCV | `results/loocv_results.json` | 보관 |

---

## 2. 현재 최고 성적 (2026-09-07 기준)

| 항목 | F1 | 정검/미검/오검 | 구성 |
|---|---|---|---|
| 배회 | **93.10** | 27/3/1 | 마지막 배회자 규칙 + ByteTrack 덤프 |
| 침입 | **92.86** | 26/4/0 | 마지막 사람 규칙 + 타일 3x3@960 + 자체 트래커 |
| 방화 | **88.89** | 8/2/0 | human_full(24k + 손라벨×5) 또는 ov10(×10) |
| 쓰러짐 | **88.89** | 8/2/0 | fall_track 트랙별 독립 판정 |

방화는 27가지 조합을 돌렸고 88.89 가 천장이었다. 미검 2편은 `C00_195_0001`·`C00_216_0003` 으로, 어떤 조합에서도 conf 0.00 이다(SR·타일·FASDD 전부 실패). 죽은 카드로 보고 규칙 쪽을 손대는 편이 낫다.

---

## 3. 다시 돌리기 전에 반드시 고칠 것

1. **`_par/*/train.txt` 경로가 전부 죽었다.** 내용이 `.../general_yolo/data/fire/...` 를 가리키는데 그 심링크는 삭제됐다. 새 경로는 `.../vms/data/학습데이터/...` 다. `par_fire.sh` 의 `mkds` 를 다시 돌려 목록을 재생성해야 한다
2. **베이스 데이터셋이 바뀌었다.** `dataset_24k`(6프레임/클립) 외에 `dataset_24k_v2`(12프레임/클립, 39,003장, train 전용)가 생겼다. 어느 쪽을 베이스로 할지 실험 축에 넣어야 한다
3. **val 이 없다.** `dataset_24k_v2` 는 val 을 비웠고 `_par/val_small.txt` 도 옛 경로를 가리킬 수 있다. 학습 모니터링용 val 경로를 먼저 정해야 한다
4. `dataset_24k` 의 val 에는 train 과 겹치는 NONE 클립 46개(276장)가 있다. 그 val 로 재는 mAP 는 낙관적이다
5. FASDD 5-fold 는 실패 원인(메모리·워커·캐시)을 먼저 잡아야 재실행 의미가 있다

---

## 4. 그리드 서치 계획 템플릿

한 번에 돌릴 조합은 `축 × 값` 으로 쓰고, **이미 돌린 조합은 위 이력에서 지우고** 시작한다.

```
베이스     dataset_24k | dataset_24k_v2
모델       yolo11n | yolo11s | yolo11m
해상도     640 | 960 | 1280
손라벨배수  x5 | x10
추가셋     없음 | fasdd_yolo | wildfire_fog_neg | _hard
에폭       60~80 (patience 30)
```

- 조합 수가 3잡 동시 실행으로 감당되는지 먼저 계산한다. yolo11s@640 30k장 80에폭 기준 잡당 약 2~3시간
- 각 잡은 `학습 → score_kisa.py(같은 imgsz, --tiles) → results/<이름>.txt` 로 끝난다
- 결과 취합은 `scripts/collect_results.py` → `results/ALL_RESULTS.md`
- 실행 후 이 문서의 "이력" 절에 값과 F1 을 추가한다
