import os
import ezdxf
from ezdxf.addons import odafc

# 修改为你的实际安装路径
exe_path = r"C:\Program Files\ODA\ODAFileConverter 27.1.0\ODAFileConverter.exe"
os.environ["ODAFC_EXECUTABLE"] = exe_path  # 设置环境变量
odafc.win_exec_path = exe_path


print(f"设置的路径: {odafc.win_exec_path}")
print(f"文件是否存在: {os.path.exists(odafc.win_exec_path)}")
print("环境变量已设置:", os.environ.get("ODAFC_EXECUTABLE"))

# 直接调用内部函数检测返回路径
try:
    from ezdxf.addons.odafc import _get_odafc_path
    detected = _get_odafc_path('windows')  # 可能需要传入system参数，默认None
    print(f"内部检测到的路径: {detected}")
except Exception as e:
    print(f"检测失败: {e}")

# 尝试转换
doc = odafc.readfile("B电气图.dwg")

# 例如，遍历模型空间中的所有实体
msp = doc.modelspace()
for entity in msp:
    print(entity)

# 如果需要，可以将加载后的文档保存为 DXF 文件
doc.saveas('B电气图_v2.dxf')