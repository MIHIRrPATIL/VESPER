"""VESPER Vision Perception Suite.

Provides:
- Device & Hardware Probing with graceful degradation (`DeviceProbe`, `DeviceCapabilities`)
- Optical Frame Acquisition (`CameraCapture`, `ScreenCapture`, `FrameCaptureResult`)
- Multimodal LPU Vision Reasoning & OCR (`GroqVisionClient`, `VisionAnalysisResult`)
- Decoupled Touchless Gesture Worker (`GestureWorker`, `GestureState`)
"""

from backend.vision.device_probe import DeviceCapabilities, DeviceProbe
from backend.vision.camera_stream import CameraCapture, ScreenCapture, FrameCaptureResult
from backend.vision.vllm import GroqVisionClient, VisionAnalysisResult
from backend.vision.gesture_service import GestureWorker, GestureState

__all__ = [
    "DeviceCapabilities",
    "DeviceProbe",
    "CameraCapture",
    "ScreenCapture",
    "FrameCaptureResult",
    "GroqVisionClient",
    "VisionAnalysisResult",
    "GestureWorker",
    "GestureState",
]
