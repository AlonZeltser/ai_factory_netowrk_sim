from visualization.experiment_visualizer import visualize_sweep_time_comparison_from_yaml

visualize_sweep_time_comparison_from_yaml(
    summary_yaml_path="../results/re_rendering/summary.yaml",
    out_dir="../results/only_collective_check",
    show=False,
    collective_time_lower_zoom_percent=15.0,
    include_collective_traffic_matrices=False,
)