Project Log Summary: Image Cropping Pipeline & GPU Utilization
1. Image Cropping Pipeline Debugging
We worked on a Python pipeline to crop document images using a YOLOv8 model.
The pipeline reads images, detects document boundaries, and saves cropped outputs, preserving the original directory structure.
We iteratively improved the cropping logic to ensure:
Correct path handling (no duplicate or missing prefixes).
Output images are saved in the correct location and format.
The cropping function maintains the original aspect ratio and ensures YOLO input dimensions are divisible by 32 (as required by the model).
2. GPU Utilization on Apple Silicon (MPS)
We confirmed that the pipeline is using the Apple Silicon GPU (MPS) by:
Adding debug logging to check the device placement of both the YOLO model and input tensors.
Monitoring system resource usage via Activity Monitor and the ps command.
Observing that multiple parallel crop.py processes increase overall GPU utilization, which is the recommended approach for maximizing throughput on MPS.
3. Performance Observations
Each crop.py process uses a moderate amount of CPU and memory, and a small but nonzero amount of GPU (as seen in Activity Monitor).
Running several parallel processes is the best way to utilize the GPU on Apple Silicon, since MPS does not support large batch sizes as efficiently as CUDA.
4. Next Steps: Model Retraining
The current YOLO model sometimes fails to crop documents accurately, even with correct scaling and aspect ratio handling.
Action Item: Retrain the YOLO model with more representative or higher-quality training data, especially if your documents have unique layouts, backgrounds, or lighting conditions.
Consider annotating a new dataset with bounding boxes that match your real-world documents.
Use the same input size (e.g., 640x640) and augmentations that reflect your actual use case.
Summary:
We debugged and improved the image cropping pipeline, ensured correct GPU utilization on Apple Silicon, and identified that retraining the YOLO model is likely necessary for better cropping accuracy.
Let me know if you want to add more technical details or need a checklist for retraining your YOLO model!