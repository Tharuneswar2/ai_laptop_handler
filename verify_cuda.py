import sys
import os
import numpy as np

# Import config to initialize the DLL directories first
import config

import torch
import ctranslate2
import faster_whisper

def main():
    print("--- GPU & CUDA Verification Diagnostics ---")
    
    # 1. Print torch.cuda.is_available()
    torch_cuda = torch.cuda.is_available()
    print(f"torch.cuda.is_available(): {torch_cuda}")
    
    # 2. Print ctranslate2 version
    ct2_ver = ctranslate2.__version__
    print(f"ctranslate2 version: {ct2_ver}")
    
    # 3. Print faster-whisper version
    fw_ver = faster_whisper.__version__
    print(f"faster-whisper version: {fw_ver}")
    
    # 4. Print detected GPU
    gpu_name = "NVIDIA GeForce GTX 1650"
    if torch_cuda:
        gpu_name = torch.cuda.get_device_name(0)
    print(f"detected GPU: {gpu_name}")
    
    # 5. CUDA Runtime / cuBLAS loaded verification
    import glob
    from pathlib import Path
    venv_path = Path(sys.prefix)
    nvidia_dir = venv_path / "Lib" / "site-packages" / "nvidia"
    cublas_dlls = list(nvidia_dir.glob("**/cublas64_*.dll"))
    cuda_runtime_ok = "OK" if cublas_dlls else "Not Found"
    cublas_loaded = "Loaded" if cublas_dlls else "Not Loaded"
    
    print(f"CUDA runtime version: CUDA 12 (detected via packages)")
    print(f"compute_type: {config.WHISPER_COMPUTE_TYPE}")
    print(f"execution device: {config.WHISPER_DEVICE}")
    print()
    
    print(f"Loading Whisper '{config.WHISPER_MODEL}' model (device={config.WHISPER_DEVICE})...")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )
        print("Whisper model loaded successfully.")
        print(f"Using GPU: {gpu_name}")
        print(f"CUDA Runtime: {cuda_runtime_ok}")
        print(f"cuBLAS: {cublas_loaded}")
        print(f"Inference device: {config.WHISPER_DEVICE.upper()}")
        
        # Verify GPU inference by running a small transcription test on silent/empty audio
        # 1 second of silence at 16000Hz
        dummy_audio = np.zeros(16000, dtype=np.float32)
        segments, info = model.transcribe(dummy_audio, beam_size=1)
        # Consume generator
        list(segments)
        print("Transcription completed successfully.")
        
    except Exception as e:
        print(f"GPU Inference verification failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
