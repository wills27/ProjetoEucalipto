# Project Code Index

Use this file as the first stop before opening source files. It is intentionally
short so navigation costs fewer tokens.

## Architecture

- `app.py`: PyQt6 entry point. Builds `CellposeWindow` by composing UI mixins.
- `ui/`: screens, presenters, dialogs, widgets, and workflow orchestration.
- `services/`: filesystem paths, config, data import, annotation, metrics, image
  rendering, and result status logic. Prefer editing these for pure behavior.
- `scripts/`: command-line jobs launched by the UI for dataset preparation,
  training, prediction, evaluation, measurement, and visualization.
- `controllers/`: Qt process execution wrapper for scripts.
- `workers/`: Qt background workers used by presenters.

## Navigation Rules

- For UI layout changes, start in `ui/page_builders.py`,
  `ui/training_page_builder.py`, or `ui/results_page_builder.py`.
- For button behavior and screen state, start in the matching
  `ui/*_presenter.py` or `ui/*_workflows.py`.
- For file layout, project folders, config paths, and derived paths, start in
  `services/paths.py` and `services/config.py`.
- For annotation/mask editing logic, start in `services/annotation.py`,
  `ui/annotation_page.py`, `ui/annotation_editor.py`, and
  `ui/mask_edit_target.py`.
- For results table/status/removal behavior, start in `services/result_service.py`,
  `ui/results_presenter.py`, `ui/result_workflows.py`, and
  `ui/result_actions.py`.
- For Cellpose execution details, start in the relevant `scripts/*.py` file, then
  check the workflow that launches it.

## Main Entry Point

- `app.py`
  - `CellposeWindow`: main window assembled from mixins.
  - `main()`: creates `QApplication`, loads config, creates window, starts event loop.

## UI Map

- `ui/page_builders.py`
  - `UiBuilderMixin`: main non-training/non-results pages and shared page setup.
- `ui/training_page_builder.py`
  - `TrainingPageBuilderMixin`: training page layout.
- `ui/results_page_builder.py`
  - `ResultsPageBuilderMixin`: results page layout.
- `ui/window_chrome.py`
  - `WindowChromeMixin`: menus, app style, chrome-level actions.
- `ui/project_presenter.py`
  - `ProjectPresenterMixin`: project selection, creation, calibration, refresh.
- `ui/model_presenter.py`
  - `ModelPresenterMixin`: model list, active model selection, model table.
- `ui/dataset_presenter.py`
  - `DatasetPresenterMixin`: dataset table, filters, splits, include/exclude state.
- `ui/dataset_import_presenter.py`
  - `DatasetImportPresenterMixin`: imports source folders into conversion input.
- `ui/dataset_preview_presenter.py`
  - `DatasetPreviewPresenterMixin`: dataset preview and mask validation feedback.
- `ui/prediction_import_presenter.py`
  - `PredictionImportPresenterMixin`: imports external prediction images.
- `ui/training_presenter.py`
  - `TrainingPresenterMixin`: parses training logs and updates training state.
- `ui/process_presenter.py`
  - `ProcessPresenterMixin`: starts/stops scripts and handles process completion.
- `ui/progress_presenter.py`
  - `ProgressPresenterMixin`: progress/status parsing for running scripts.
- `ui/script_workflows.py`
  - `ScriptWorkflowMixin`: launches prepare/train/predict/evaluate scripts.
- `ui/annotation_workflow.py`
  - `AnnotationWorkflowMixin`: launches annotation-related script flows.
- `ui/result_workflows.py`
  - `ResultWorkflowMixin`: result generation, viewing, and workflow actions.
- `ui/results_presenter.py`
  - `ResultsPresenterMixin`: result table presentation and refresh.
- `ui/result_actions.py`
  - `ResultActionsMixin`: result removal, mask editing, overlay refresh actions.
- `ui/analysis_presenter.py`
  - `AnalysisPresenterMixin`: metrics, measurement tables, image/overlay previews.
- `ui/annotation_page.py`
  - `AnnotationPage`: interactive dataset annotation widget.
- `ui/annotation_editor.py`
  - `AnnotationEditorDialog`: mask editor dialog.
- `ui/mask_edit_target.py`
  - `DatasetMaskTarget`, `ResultMaskTarget`: read/write targets for mask edits.
- `ui/loss_plot.py`
  - `LossPlotWidget`: matplotlib loss chart.
- `ui/widgets.py`
  - `AnnotationPreviewLabel`: reusable preview image label.
- `ui/tables/dataset_pairs_table.py`
  - `DatasetPairsTable`: dataset table context menu behavior.
- `ui/dialogs/*.py`
  - `CalibrationDialog`, `ErrorDialog`, `ResultsViewerDialog`.

## Services Map

- `services/paths.py`: project/config paths, folder creation, active model/results paths.
- `services/config.py`: load/save app config and legacy migration.
- `services/annotation.py`: mask validation, loading, drawing, brushing, saving.
- `services/cell_measurements.py`: cell measurement and CSV row generation.
- `services/conversion_scan.py`: scans conversion input image/mask pairs.
- `services/csv_files.py`: semicolon CSV helpers and row removal.
- `services/dataset_import.py`: import and convert dataset images.
- `services/dataset_plan.py`: dataset plan load/save/split helpers.
- `services/dataset_preview.py`: builds dataset preview image.
- `services/dataset_service.py`: dataset rows, filters, summaries, removal targets.
- `services/image_arrays.py`: numpy image normalization.
- `services/metrics.py`: metric CSV loading and summaries.
- `services/model_service.py`: model list and default model lookup.
- `services/overlay_rendering.py`: mask overlays, IDs, and measurement overlays.
- `services/prediction_import.py`: prediction import discovery/naming/conversion.
- `services/process_output.py`: progress and error parsing.
- `services/result_service.py`: result entries, status indexes, output paths/removal.
- `services/training_log_parser.py`: training log cleaning/parsing.

## Scripts Map

- `scripts/prepare_dataset.py`: creates train/val/test data from conversion input.
- `scripts/train_cellpose.py`: trains Cellpose model and logs progress/loss.
- `scripts/predict_cellpose.py`: predicts masks for input images.
- `scripts/generate_results.py`: predicts masks and creates visual overlays.
- `scripts/evaluate_cellpose.py`: compares ground truth and predicted masks.
- `scripts/measure_cells.py`: measures cells and writes CSV outputs.
- `scripts/visualize_predictions.py`: creates overlay images from predictions.
- `scripts/create_mask_with_model.py`: creates a mask for a single image/model.
- `scripts/compact_masks.py`: compacts Cellpose `_seg.npy` masks to TIF masks.

## Process And Background Work

- `controllers/process_runner.py`
  - `ScriptProcessRunner`: QProcess wrapper with stdout/stderr/progress signals.
- `workers/dataset_scan_worker.py`
  - `DatasetScanWorker`: scans dataset conversion rows in a worker.
- `workers/file_copy_worker.py`
  - `FileCopyWorker`: background file copy/import with progress.

## Common Change Targets

- Add or rename a project folder: `services/paths.py`, then any presenter using it.
- Change saved config fields: `services/config.py`, `app_config.json`, presenters that save config.
- Change dataset table columns or filters: `ui/dataset_presenter.py`,
  `ui/tables/dataset_pairs_table.py`, `services/dataset_service.py`.
- Change train/predict command arguments: `ui/script_workflows.py`,
  `ui/annotation_workflow.py`, `ui/result_workflows.py`, and matching script.
- Change result status detection: `services/result_service.py` and
  `ui/results_presenter.py`.
- Change mask drawing/editing: `services/annotation.py`, `ui/annotation_page.py`,
  `ui/annotation_editor.py`, `ui/mask_edit_target.py`.
- Change measurement output: `services/cell_measurements.py`,
  `scripts/measure_cells.py`, and result/analysis presenters.

## Large Files To Open Last

Open these only after checking this index and using `rg` for the exact symbol:

- `ui/annotation_page.py`
- `ui/dataset_presenter.py`
- `ui/analysis_presenter.py`
- `ui/result_actions.py`
- `ui/result_workflows.py`
- `services/annotation.py`
- `services/cell_measurements.py`
- `scripts/prepare_dataset.py`

