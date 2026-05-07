"""
坐标处理模块

提供坐标映射功能。
"""

import os
from typing import List, Optional, Tuple, Union

from baodou_ai.core.config import Config
from baodou_ai.platform import get_platform_adapter


class CoordinateMapper:
    """坐标映射类"""
    
    def __init__(self, config: Optional[Config] = None):
        self._config = config or Config()
        self._platform_adapter = get_platform_adapter()
    
    def map_to_screen(
        self,
        x: float,
        y: float,
        screen_width: int,
        screen_height: int,
    ) -> Tuple[float, float]:
        """
        将AI返回的1000x1000像素坐标映射到实际屏幕坐标
        
        Args:
            x: AI返回的x坐标（1000x1000坐标系）
            y: AI返回的y坐标（1000x1000坐标系）
            screen_width: 实际屏幕宽度
            screen_height: 实际屏幕高度
        
        Returns:
            Tuple[float, float]: 实际屏幕上的坐标
        """
        x = max(-100000, min(100000, x))
        y = max(-100000, min(100000, y))
        
        x_real = (x / 1000.0) * screen_width
        y_real = (y / 1000.0) * screen_height
        
        x_real = max(0, min(100000, x_real))
        y_real = max(0, min(100000, y_real))
        
        return x_real, y_real
    
    def _resolve_path(self, path: str) -> str:
        """解析路径"""
        if os.path.isabs(path):
            return path
        
        resolved = self._platform_adapter.get_resource_path(path)
        return resolved if resolved else path
    
    def _parse_coordinates_from_str(self, coordinates_str: str) -> Union[List, Tuple]:
        """从字符串解析坐标"""
        import re
        try:
            import json
            parsed = json.loads(coordinates_str)
            if isinstance(parsed, list) and len(parsed) >= 2:
                if isinstance(parsed[0], (list, tuple)):
                    return [[float(x) for x in point] for point in parsed]
                else:
                    return [float(x) for x in parsed]
        except:
            pass
        
        try:
            numbers = re.findall(r'-?\d+\.?\d*', coordinates_str)
            if len(numbers) >= 4:
                return [
                    [float(numbers[0]), float(numbers[1])],
                    [float(numbers[2]), float(numbers[3])]
                ]
            elif len(numbers) >= 2:
                return [float(numbers[0]), float(numbers[1])]
        except:
            pass
        
        return [0, 0]
    
    def validate_coordinates(
        self,
        coordinates: Union[List, Tuple, str],
        scale: float = 1.0
    ) -> Union[List, Tuple]:
        """
        验证并修复坐标数据
        
        Args:
            coordinates: 坐标数据（支持字符串格式）
            scale: 缩放比例
        
        Returns:
            修复后的坐标数据
        """
        def validate_value(val):
            if isinstance(val, (int, float)):
                return max(-100000, min(100000, val))
            return val
        
        if isinstance(coordinates, str):
            coordinates = self._parse_coordinates_from_str(coordinates)
        
        if not isinstance(coordinates, (list, tuple)):
            print(f"坐标数据类型错误: {type(coordinates)}, 值: {coordinates}")
            return [0, 0]
        
        if len(coordinates) < 2:
            print(f"坐标数据长度不足: {coordinates}")
            return [0, 0]
        
        if isinstance(coordinates[0], (list, tuple)):
            if len(coordinates) == 1:
                return [
                    validate_value(coordinates[0][0]),
                    validate_value(coordinates[0][1])
                ]
            else:
                return [
                    [validate_value(coordinates[0][0]), 
                     validate_value(coordinates[0][1])],
                    [validate_value(coordinates[1][0]), 
                     validate_value(coordinates[1][1])]
                ]
        else:
            return [validate_value(coordinates[0]), 
                    validate_value(coordinates[1])]
