"""
=============================================================
AGENTE v14 - Diagnostico de GPU para Ollama
=============================================================
Verifica si Ollama esta usando la GPU correctamente.
Ejecutar: python check_gpu.py
=============================================================
"""

import subprocess
import shlex
import json
import sys
import time


def run_cmd(cmd):
    """Ejecuta un comando y retorna la salida."""
    try:
        result = subprocess.run(
            shlex.split(cmd), capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip(), result.returncode
    except Exception as e:
        return str(e), -1


def check_nvidia_driver():
    """Verifica si el driver NVIDIA esta instalado."""
    print("\n" + "="*60)
    print("1. VERIFICANDO DRIVER NVIDIA")
    print("="*60)
    
    output, code = run_cmd("nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader")
    if code == 0 and output:
        print(f"   GPU detectada: {output}")
        # Parsear info
        parts = [p.strip() for p in output.split(",")]
        if len(parts) >= 3:
            print(f"   Nombre: {parts[0]}")
            print(f"   Driver: {parts[1]}")
            print(f"   VRAM: {parts[2]}")
        return True
    else:
        print("   NO se detecto GPU NVIDIA o nvidia-smi no esta instalado")
        print("   -> Instala los drivers NVIDIA desde: https://www.nvidia.com/drivers")
        return False


def check_ollama_status():
    """Verifica si Ollama esta corriendo y que modelo esta cargado."""
    print("\n" + "="*60)
    print("2. VERIFICANDO ESTADO DE OLLAMA")
    print("="*60)
    
    # Check si Ollama esta corriendo
    import urllib.request
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", [])
            print(f"   Ollama esta corriendo en localhost:11434")
            print(f"   Modelos instalados: {len(models)}")
            for m in models:
                name = m.get("name", "?")
                size = m.get("size", 0)
                size_gb = size / (1024**3) if size else 0
                print(f"     - {name} ({size_gb:.1f} GB)")
    except Exception as e:
        print(f"   ERROR: No se puede conectar a Ollama: {e}")
        print("   -> Asegurate de que Ollama este corriendo (ollama serve)")
        return False
    
    # Check modelo cargado y si usa GPU
    output, code = run_cmd("ollama ps")
    if code == 0 and output:
        print(f"\n   Modelo actualmente cargado:")
        for line in output.split("\n"):
            if line.strip():
                print(f"     {line}")
        
        # Ver si dice CPU o GPU
        if "100% CPU" in output:
            print("\n   *** PROBLEMA DETECTADO: El modelo esta 100% en CPU! ***")
            print("   -> Esto explica la lentitud. Ver seccion de soluciones abajo.")
            return False
        elif "GPU" in output:
            print("\n   OK: El modelo esta usando GPU.")
            return True
        else:
            print("\n   No se pudo determinar si usa GPU o CPU.")
            return None
    else:
        print("\n   No hay modelo cargado actualmente.")
        print("   -> Ejecuta una consulta al agente y luego corre este script de nuevo.")
        return None


def check_gpu_during_inference():
    """Verifica el uso de GPU durante inferencia."""
    print("\n" + "="*60)
    print("3. TEST DE INFERENCIA (verificando GPU en accion)")
    print("="*60)
    
    import urllib.request
    
    # Primero verificar VRAM antes de inferencia
    vram_before, _ = run_cmd("nvidia-smi --query-gpu=memory.used --format=csv,noheader")
    print(f"   VRAM antes: {vram_before}")
    
    # Hacer una inferencia corta
    print("   Ejecutando inferencia corta...")
    try:
        payload = json.dumps({
            "model": "llama3.1:8b",
            "messages": [{"role": "user", "content": "Di hola"}],
            "stream": False
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        start = time.time()
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - start
            content = result.get("message", {}).get("content", "")
            print(f"   Tiempo de respuesta: {elapsed:.1f}s")
            print(f"   Respuesta: {content[:80]}...")
    except Exception as e:
        print(f"   Error en inferencia: {e}")
        return
    
    # Verificar VRAM despues
    vram_after, _ = run_cmd("nvidia-smi --query-gpu=memory.used --format=csv,noheader")
    print(f"   VRAM despues: {vram_after}")
    
    # Verificar ollama ps ahora
    output, code = run_cmd("ollama ps")
    if code == 0:
        for line in output.split("\n"):
            if "qwen" in line.lower() or "PROCESSOR" in line:
                print(f"   {line.strip()}")
        
        if "100% CPU" in output:
            print("\n   *** PROBLEMA: El modelo esta corriendo 100% en CPU ***")
        elif "GPU" in output:
            gpu_pct = "100% GPU" if "100% GPU" in output else "Parcial GPU"
            print(f"\n   OK: GPU en uso ({gpu_pct})")


def check_environment():
    """Verifica variables de entorno relevantes para GPU."""
    print("\n" + "="*60)
    print("4. VARIABLES DE ENTORNO GPU")
    print("="*60)
    
    import os
    
    env_vars = {
        "CUDA_VISIBLE_DEVICES": "Especifica que GPU usar (0 = primera NVIDIA)",
        "OLLAMA_LLM_LIBRARY": "Fuerza libreria LLM (cuda_v11, cuda_v12, cpu)",
        "OLLAMA_HOST": "Host de Ollama",
        "OLLAMA_KEEP_ALIVE": "Tiempo que modelo permanece en memoria",
        "OLLAMA_MAX_VRAM": "Max VRAM a usar (bytes)",
    }
    
    for var, desc in env_vars.items():
        val = os.environ.get(var, "(no definida)")
        status = "" if val == "(no definida)" else " <-- DEFINIDA"
        print(f"   {var} = {val}{status}")
        print(f"     {desc}")


def print_solutions():
    """Imprime soluciones para problemas comunes de GPU."""
    print("\n" + "="*60)
    print("5. SOLUCIONES SI LA GPU NO SE USA")
    print("="*60)
    
    print("""
   SOLUCION A: Forzar GPU NVIDIA en Windows (Laptops con doble GPU)
   -----------------------------------------------------------------
   1. Panel de Control NVIDIA > Manage Display Mode > "Nvidia GPU only"
   2. O: Configuracion de Windows > Sistema > Pantalla > Graficos
      -> Buscar "ollama" -> Opciones > "Alto rendimiento" (NVIDIA)
   3. Reiniciar Ollama (cerrar de la bandeja y abrir de nuevo)

   SOLUCION B: Variable de entorno CUDA_VISIBLE_DEVICES
   -----------------------------------------------------
   1. Win+R -> sysdm.cpl -> Avanzado -> Variables de entorno
   2. Nueva variable de usuario:
      Nombre: CUDA_VISIBLE_DEVICES
      Valor: 0
   3. Reiniciar Ollama

   SOLUCION C: Forzar libreria CUDA
   ---------------------------------
   1. Crear variable de entorno:
      Nombre: OLLAMA_LLM_LIBRARY
      Valor: cuda_v12
   2. Reiniciar Ollama
   3. Si no funciona, probar: cuda_v11

   SOLUCION D: Verificar driver NVIDIA
   ------------------------------------
   1. nvidia-smi debe mostrar driver version 531+
   2. Si es menor, actualizar desde nvidia.com/drivers
   3. Si el driver es muy nuevo y Ollama no lo detecta,
      intentar downgrade a version estable

   SOLUCION E: Deshabilitar Vulkan (si interfiere)
   ------------------------------------------------
   1. Crear variable de entorno:
      Nombre: OLLAMA_VULKAN
      Valor: 0
   2. Reiniciar Ollama

   IMPORTANTE: Despues de cambiar variables de entorno,
   debes REINICIAR Ollama (cerrar de la bandeja del sistema).
""")


def main():
    print("="*60)
    print("   AGENTE v14 - DIAGNOSTICO DE GPU PARA OLLAMA")
    print("="*60)
    
    gpu_ok = check_nvidia_driver()
    ollama_ok = check_ollama_status()
    
    if gpu_ok:
        check_gpu_during_inference()
    
    check_environment()
    print_solutions()
    
    print("\n" + "="*60)
    print("   RESUMEN")
    print("="*60)
    if not gpu_ok:
        print("   GPU NVIDIA NO detectada o driver no instalado")
        print("   -> El agente correra en CPU (MUY LENTO)")
        print("   -> Instala drivers NVIDIA y reinicia Ollama")
    elif ollama_ok is False:
        print("   GPU detectada PERO Ollama NO la esta usando")
        print("   -> Aplica las soluciones de arriba")
        print("   -> La solucion mas comun: Panel de Control NVIDIA > Alto rendimiento")
    elif ollama_ok is True:
        print("   GPU esta siendo usada correctamente por Ollama")
        print("   -> Si sigue lento, el problema puede ser:")
        print("      - Modelo demasiado grande para la VRAM disponible")
        print("      - Muchas iteraciones ReAct (max 8)")
        print("      - Llamadas de embedding innecesarias")
    else:
        print("   No se pudo determinar el estado de la GPU")
        print("   -> Ejecuta una consulta al agente y luego repite este diagnostico")
    
    print()


if __name__ == "__main__":
    main()
