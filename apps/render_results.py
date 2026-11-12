from visualization.experiment_visualizer import visualize_sweep_time_comparison_from_yaml

visualize_sweep_time_comparison_from_yaml(
    summary_yaml_path="../results/re_rendering/summary.yaml",
    out_dir="../results/only_training_step_check",
    show=False,
    training_step_time_lower_zoom_percent=15.0,
    include_training_step_traffic_matrices=False,
    paper_style=True,
)