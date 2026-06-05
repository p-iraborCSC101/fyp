"""Launch the full emergency-response stack inside Gazebo Sim.

Usage:
    ros2 launch emergency_launch emergency_sim.launch.py \
        planner_mode:=a_star \
        scenario:=low_crowding \
        run_id:=1 \
        seed:=42 \
        headless:=false
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import (
    LaunchConfiguration,
    PathJoinSubstitution,
    TextSubstitution,
)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    planner_mode = LaunchConfiguration('planner_mode')
    scenario = LaunchConfiguration('scenario')
    run_id = LaunchConfiguration('run_id')
    seed = LaunchConfiguration('seed')
    headless = LaunchConfiguration('headless')

    pkg_share = FindPackageShare('emergency_launch')

    # World file selected by scenario name: hospital_<scenario>.sdf
    world_file = PathJoinSubstitution([
        pkg_share, 'worlds', [TextSubstitution(text='hospital_'), scenario, TextSubstitution(text='.sdf')],
    ])

    # Scenario YAML used by the planner and the publisher
    scenario_file = PathJoinSubstitution([
        pkg_share, 'scenarios', [scenario, TextSubstitution(text='.yaml')],
    ])

    rviz_config = PathJoinSubstitution([pkg_share, 'rviz', 'emergency_nav.rviz'])

    gz_sim_gui = ExecuteProcess(
        cmd=['gz', 'sim', '-r', '-v', '2', world_file],
        output='screen',
        condition=UnlessCondition(headless),
    )
    gz_sim_headless = ExecuteProcess(
        cmd=['gz', 'sim', '-r', '-s', '-v', '2', world_file],
        output='screen',
        condition=IfCondition(headless),
    )

    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            # cmd_vel: ROS Twist -> Gazebo Twist
            '/model/medibot/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
            # odometry: Gazebo Odometry -> ROS Odometry
            '/model/medibot/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry',
            # clock so RViz/TF use sim time consistently
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
        ],
        output='screen',
    )

    static_tf_map_to_odom = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='map_to_odom',
        arguments=['0', '0', '0', '0', '0', '0', 'map', 'odom'],
        output='screen',
    )

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        output='screen',
        condition=UnlessCondition(headless),
    )

    sensor_simulator = Node(
        package='emergency_sensing',
        executable='sensor_simulator',
        name='sensor_simulator',
        output='screen',
        parameters=[{
            'scenario_file': scenario_file,
            'run_id': run_id,
            'seed': seed,
            'first_alert_delay_s': 4.0,
            'alert_period_s': 30.0,
        }],
    )

    alert_fusion = Node(
        package='emergency_sensing',
        executable='alert_fusion',
        name='alert_fusion',
        output='screen',
        parameters=[{
            'scenario_file': scenario_file,
            'run_id': run_id,
            'seed': seed,
            'heart_rate_threshold': 120,
        }],
    )

    sensor_dashboard = Node(
        package='emergency_sensing',
        executable='sensor_dashboard',
        name='sensor_dashboard',
        output='screen',
    )

    human_obstacles = Node(
        package='human_obstacles',
        executable='human_obstacles_node',
        name='human_obstacles',
        output='screen',
        parameters=[{
            'frame_id': 'world',
            'scenario_file': scenario_file,
            'publish_rate_hz': 10.0,
            'use_sim_time': True,
        }],
    )

    path_planner = Node(
        package='path_planner',
        executable='path_planner',
        name='path_planner',
        output='screen',
        parameters=[{
            'planner_mode': planner_mode,
            'scenario_file': scenario_file,
            'seed': seed,
            'rrt_max_iterations': 2000,
            'rrt_step_size': 0.8,
            'rrt_goal_sample_rate': 0.25,
            'max_predictive_replans': 20,
        }],
    )

    robot_controller = Node(
        package='robot_control',
        executable='robot_controller',
        name='robot_controller',
        output='screen',
        remappings=[
            ('/cmd_vel', '/model/medibot/cmd_vel'),
            ('/odom', '/model/medibot/odometry'),
        ],
        parameters=[{
            'grid_scale': 1.0,
            'max_linear_speed': 0.45,
            'max_angular_speed': 1.5,
            'waypoint_tolerance': 0.4,
            'linear_gain': 0.8,
            'angular_gain': 2.2,
            'stall_timeout_s': 2.5,
            'stall_min_cmd_linear': 0.05,
        }],
    )

    response_logger = Node(
        package='response_logger',
        executable='response_logger',
        name='response_logger',
        output='screen',
        parameters=[{
            'scenario': scenario,
            'planner': planner_mode,
            'run_id': run_id,
            'arrival_timeout_s': 90.0,
        }],
    )

    caregiver_notify = Node(
        package='caregiver_notify',
        executable='caregiver_notify_node',
        name='caregiver_notify',
        output='screen',
        parameters=[{
            'cooldown_s': 10.0,
            'caregiver_id': 'ward-a',
        }],
    )

    return LaunchDescription([
        DeclareLaunchArgument('planner_mode', default_value='a_star',
                              description='Planner mode: a_star or rrt_star'),
        DeclareLaunchArgument('scenario', default_value='low_crowding',
                              description='Scenario name: low_crowding | moderate_crowding | high_crowding'),
        DeclareLaunchArgument('run_id', default_value='1',
                              description='Run identifier for this trial (used in CSV row).'),
        DeclareLaunchArgument('seed', default_value='42',
                              description='Random seed for the scenario / dynamic events.'),
        DeclareLaunchArgument('headless', default_value='false',
                              description='Run gz sim with -s (no GUI). Use true for batch trials.'),

        gz_sim_gui,
        gz_sim_headless,
        bridge,
        static_tf_map_to_odom,
        rviz,
        sensor_simulator,
        alert_fusion,
        sensor_dashboard,
        human_obstacles,
        path_planner,
        robot_controller,
        response_logger,
        caregiver_notify,
    ])
