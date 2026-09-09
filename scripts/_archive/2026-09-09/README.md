# scripts 보관 2026-09-09

삭제하지 않고 이동만 했다. 되살리려면 `git mv` 또는 `mv` 로 scripts/ 에 돌려놓는다.
현역 진입점: `model.py`(학습) · `score_kisa.py`(방화 채점) · `scripts/exp_queue.py`(실험 큐) · `scripts/build_humanset.py`(손라벨→학습셋)

| 파일 | 사유 |
|---|---|
| _exp_dfire.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| _exp_fire_snowmix.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| _exp_queue.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| _exp_queue2.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| _exp_queue3.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| _wildfire_labels.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| analyze_all.py | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| build_hardsets.py | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| clean24k.py | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| dump_lf.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| exp_queue.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| fall_kpts.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fasdd_kfold.py | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fasdd_to_yolo.py | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fda_build.py | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fda_preview.py | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fda_x_train.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_ablation.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_chain.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| fire_fasdd.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_fasdd_core.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_grid.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_human_full.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_human_pilot.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_kfold.py | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_matrix.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_matrix2.py | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_matrix2.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| fire_seq.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_v2.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_v3.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_v4.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| fire_x_plain.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| g20_day1.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| g20_fall.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| gpu_queue.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| int_tile.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| make_960.py | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| make_variants.py | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| night.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| night2.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| night3_snowfog.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| night4_fasdd.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| night5_kfold.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| night6_fast.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| night6_retry.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| par_fire.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| par_fire_drivers.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| person_redump.py.orig | 백업 사본(.orig) |
| person_v1.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| person_v2.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| person_v4.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| pl_ir_fire.py | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| pose_v1.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| pose_v2.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| prep71953.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| rtdetr.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| run_kisa_runs.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| train_fog.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| trk_redump.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| v3_chain.sh | 삭제/개명된 경로 참조(dataset_24k·datasets/·open_coco 등) → 실행 불가 |
| watch_and_score.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
| watchdog.sh | exp_queue.py 로 대체된 큐/드라이버·완료된 1회성 |
