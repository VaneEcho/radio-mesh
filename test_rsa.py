"""最小化 RSA306B 诊断脚本"""
import sys
import time
import rsa_api

SO_DIR = "/home/chuan/radio-mesh/docs/RSA_API-1.0.0014/"

print("1. 加载 RSA API 库 ...")
rsa = rsa_api.RSA(so_dir=SO_DIR)
print("   OK")

print("2. 搜索设备 ...")
found = rsa.DEVICE_Search()
print(f"   找到: {found}")
if not found:
    sys.exit("未找到设备")

print("3. 连接设备 ...")
rsa.DEVICE_Connect(0)
print("   OK")

print("4. 获取当前 spectrum 设置 ...")
settings = rsa.SPECTRUM_GetSettings()
print(f"   当前设置: {settings}")

print("5. 跳过 SetCenterFreq，使用默认 1500 MHz")

print("6. 跳过所有设置，直接使用默认值")

print("8. 启用 spectrum 测量 ...")
rsa.SPECTRUM_SetEnable(True)
print("   OK")

print("9. DEVICE_Run ...")
rsa.DEVICE_Run()
print("   OK")

print("10. SPECTRUM_AcquireTrace ...")
rsa.SPECTRUM_AcquireTrace()
print("    OK")

print("11. 等待数据就绪 (5000 ms) ...")
ready = rsa.SPECTRUM_WaitForTraceReady(5000)
print(f"   ready={ready}")

if ready:
    print("12. 获取 trace 数据 ...")
    data, length = rsa.SPECTRUM_GetTrace("Trace1", 801)
    print(f"    获取到 {length} 个点, 前5个: {list(data[:5])}")
else:
    print("12. 超时，未获取到数据")

print("13. DEVICE_Stop ...")
rsa.DEVICE_Stop()
print("    OK")

print("14. 断开连接 ...")
rsa.DEVICE_Disconnect()
print("    完成！")
