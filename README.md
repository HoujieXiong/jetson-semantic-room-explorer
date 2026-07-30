# Jetson Semantic Room Explorer

Autonomous semantic room exploration and object memory on Jetson Orin Nano.

## Goal

Build a robot-facing system that can explore an indoor environment, estimate camera pose with RGB-D SLAM, detect objects with an edge-optimized YOLO pipeline, localize objects in 3D, and maintain persistent object memory.

The system should eventually support queries such as:

```text
Where is the bottle?
What objects have been seen in this room?
Where did I last see my backpack?
```

## Core Idea

This project is not just a YOLO demo. The goal is to connect perception, mapping, and memory:

```text
RGB-D camera
-> RTAB-Map RGB-D SLAM
-> YOLO object detection
-> depth-based 3D localization
-> map-frame object fusion
-> persistent semantic memory
-> query / visualization
```

The key transformation is:

```text
map_T_object = map_T_camera * camera_T_object
```

RTAB-Map provides the camera pose in the map frame. YOLO and depth provide the object position in the camera frame. Together, the system stores object locations in a persistent room-level memory.

## Hardware

Target hardware:

- Jetson Orin Nano
- RGB-D camera, planned
- Optional mobile robot base
- Optional DisplayPort dummy plug for headless remote desktop

Current development mode:

- Jetson Orin Nano
- JetPack 6.2.2
- SSH / headless workflow
- Image/video-file inference before live camera is available
- YOLOv8n image inference running on Jetson GPU

## Software Stack

Planned stack:

- Ubuntu 22.04
- JetPack 6.2.2
- ROS2 Humble
- RTAB-Map RGB-D SLAM
- YOLO object detection
- ONNX
- TensorRT FP16
- OpenCV
- Python
- C++ where performance-critical
- RViz visualization

Current verified ML environment:

- Python 3.10.12
- PyTorch 2.8.0
- TorchVision 0.23.0
- CUDA available on Orin GPU
- NumPy 1.26.4
- OpenCV 4.10.0 headless
- Ultralytics 8.4.112

## Project Phases

### Phase 1: Jetson Bring-Up

Status: mostly complete

Goals:

- Set up Jetson Orin Nano
- Confirm JetPack, CUDA, TensorRT, Python, and disk/memory state
- Create reproducible project structure
- Configure Git and GitHub
- Establish headless SSH workflow

Deliverables:

- Environment snapshot
- Project repository
- Basic Python/OpenCV validation
- Jetson-compatible PyTorch / TorchVision with CUDA validation

### Phase 2: YOLO Perception Baseline

Status: in progress

Goals:

- Run YOLO on still images
- Run YOLO on video files
- Save annotated outputs without GUI
- Measure baseline PyTorch latency and FPS

Deliverables:

- Image inference script
- Video inference script
- Annotated output images/videos
- Baseline benchmark table

Current milestone:

```text
YOLOv8n PyTorch inference runs on Jetson Orin Nano GPU.
Test input: data/sample_images/test.jpg
Detected classes: person, cars, trains, traffic light
Model inference latency: 34.0 ms
Preprocess latency: 44.0 ms
Postprocess latency: 35.8 ms
Input tensor shape: (1, 3, 448, 640)
Output directory: runs/detect/data/outputs/yolo_smoke_test
```

### Phase 3: TensorRT Deployment

Goals:

- Export YOLO model to ONNX
- Build TensorRT FP16 engine
- Compare PyTorch vs TensorRT inference
- Measure latency, FPS, memory, and power mode

Deliverables:

- ONNX export script
- TensorRT engine build script
- Benchmark script
- Benchmark results

### Phase 4: RGB-D 3D Object Localization

Goals:

- Use aligned RGB and depth frames
- Estimate object depth from detection bounding boxes
- Back-project detections into 3D camera coordinates
- Publish or log 3D object detections

Core math:

```text
X = (u - cx) * Z / fx
Y = (v - cy) * Z / fy
Z = depth
```

Depth strategy:

```text
bbox ROI
-> filter invalid depth
-> median depth
-> 3D object position
```

Deliverables:

- 3D localization script/node
- Object coordinate logs
- Error/stability analysis

### Phase 5: RTAB-Map RGB-D SLAM

Goals:

- Run RTAB-Map with RGB-D input
- Estimate camera pose
- Build room map
- Publish TF/map frame information
- Visualize map in RViz

Deliverables:

- RTAB-Map launch/config files
- Map output
- Camera trajectory
- RViz visualization

### Phase 6: Semantic Object Memory

Goals:

- Transform object detections from camera frame to map frame
- Merge repeated detections across time
- Store persistent object memory
- Support object queries

Object memory fields:

```text
object_id
class_name
confidence
map_position_xyz
observation_count
first_seen
last_seen
source_frames
```

Example query:

```text
find bottle
```

Example output:

```text
bottle_01 at map position [x, y, z], seen 5 times
```

Deliverables:

- Object memory database
- Query script/service
- Semantic map visualization

### Phase 7: Exploration Behavior

Goals:

- Use map coverage or frontier-style logic to guide exploration
- Support manual, semi-autonomous, or robot-base exploration modes
- Update semantic memory during exploration

Mobility backends:

- Handheld RGB-D scan
- Recorded RGB-D sequence
- Mobile robot base, optional
- Simulated robot, optional

Deliverables:

- Exploration policy prototype
- Semantic room exploration demo
- Final demo video

## Performance Priorities

The project prioritizes robotics system usefulness over single-frame ML metrics.

Priority order:

1. System stability and real-time operation
2. Camera pose and map-frame consistency
3. Stable 3D object localization
4. YOLO detection accuracy
5. Visual quality and high resolution

Design principle:

```text
A slightly smaller detector running reliably in real time is more useful than a heavier detector that causes SLAM drops, high latency, or memory pressure.
```

## Initial Repository Structure

```text
jetson-semantic-room-explorer/
  README.md
  docs/
  scripts/
  src/
  data/
    sample_images/
    sample_videos/
    outputs/
  models/
  benchmarks/
```

## Current Status

- [X] Project scope defined
- [X] JetPack 6.2.2 installed
- [X] SSH access available
- [X] Headless workflow selected
- [X] GitHub repository initialized
- [X] Environment snapshot saved
- [X] Python/OpenCV baseline verified
- [X] Jetson-compatible PyTorch CUDA verified
- [X] YOLO image inference running
- [ ] YOLO inference script added
- [ ] YOLO baseline benchmark table added
- [ ] TensorRT benchmark complete
- [ ] RGB-D camera integrated
- [ ] RTAB-Map RGB-D SLAM running
- [ ] Semantic object memory implemented

## Resume-Oriented Summary

Planned final description:

```text
Built a Jetson Orin Nano-based semantic room exploration system that combines RTAB-Map RGB-D SLAM, TensorRT-optimized YOLO object detection, depth-based 3D localization, and persistent object memory to support robot-facing queries about objects in indoor environments.
```

## Notes

This project is designed to be robot-base agnostic. The core contribution is semantic perception and memory. A mobile robot base can consume the resulting target/object poses later, but the system can also be developed and validated with handheld RGB-D scans, recorded sequences, or headless Jetson inference.
