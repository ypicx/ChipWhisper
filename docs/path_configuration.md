# 路径配置

## 目标

把这些和本机环境强相关的路径从代码里拿出来，让用户可以自己调：

- `Keil UV4.exe`
- `STM32CubeMX` 安装目录
- `STM32Cube Repository`
- `STM32Cube_FW_F1` 固件包目录
- `STM32Cube_FW_G4` 固件包目录

## 优先级

路径解析按这个顺序生效：

1. 命令行显式参数
2. 环境变量
3. `stm32_agent.paths.json`
4. 自动发现的常见默认路径

## 配置文件

仓库根目录支持：

- `stm32_agent.paths.json`

也提供了一个示例：

- `stm32_agent.paths.example.json`

示例内容：

```json
{
  "keil_uv4_path": "D:\\Keil_v5\\UV4\\UV4.exe",
  "keil_fromelf_path": "D:\\Keil_v5\\ARM\\ARMCLANG\\bin\\fromelf.exe",
  "stm32cubemx_install_path": "D:\\STM32CubeMX",
  "stm32cube_repository_path": "C:\\Users\\YOUR_NAME\\STM32Cube\\Repository",
  "stm32cube_f1_package_path": "C:\\Users\\YOUR_NAME\\STM32Cube\\Repository\\STM32Cube_FW_F1_V1.8.7",
  "stm32cube_g4_package_path": "C:\\Users\\YOUR_NAME\\STM32Cube\\Repository\\STM32Cube_FW_G4_V1.6.2"
}
```

## 命令

初始化配置文件：

```powershell
python -m stm32_agent init-paths
```

查看当前解析结果：

```powershell
python -m stm32_agent doctor-paths
```

检查本机是否已下载 `STM32Cube_FW_F1`：

```powershell
python -m stm32_agent doctor-cubef1
```

检查本机是否已下载 `STM32Cube_FW_G4`：

```powershell
python -m stm32_agent doctor-cubeg4
```

把本机固件包里的 `Drivers` 导入到生成工程：

```powershell
python -m stm32_agent import-cubef1-drivers .\out\custom_project_v9
```

如果目标是 `STM32G431RBT6 / STM32G4`：

```powershell
python -m stm32_agent import-cubeg4-drivers .\out\g431_running_leds_project
```

检查某个工程是否满足 Keil 构建条件：

```powershell
python -m stm32_agent doctor-keil .\out\custom_project_v9
```

## 当前已验证路径

这台机器上已经验证过：

- `Keil UV4.exe`: `D:\Keil_v5\UV4\UV4.exe`
- `Keil fromelf.exe`: `D:\Keil_v5\ARM\ARMCLANG\bin\fromelf.exe`
- `STM32CubeMX`: `D:\STM32CubeMX`
- `STM32Cube Repository`: `C:\Users\YOUR_NAME\STM32Cube\Repository`
- `STM32Cube_FW_F1`: `C:\Users\YOUR_NAME\STM32Cube\Repository\STM32Cube_FW_F1_V1.8.7`
- `STM32Cube_FW_G4`: `C:\Users\YOUR_NAME\STM32Cube\Repository\STM32Cube_FW_G4_V1.6.2`

## 建议

- 换机器时先跑一次 `init-paths`
- 开始构建前先跑 `doctor-paths`
- 导入 Drivers 前先跑 `doctor-cubef1`
- G4 工程导入 Drivers 前先跑 `doctor-cubeg4`
- 真正编译前先跑 `doctor-keil`
- 如果希望自动导出 `.hex`，确认 `doctor-keil` 输出里已经识别到 `fromelf_path`
