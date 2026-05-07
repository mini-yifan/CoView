"""
包豆电脑 API 使用示例

本文件展示如何在其他项目中使用包豆电脑的 API。
"""

import time

from baodou_ai import BaodouAI, execute_task


def example_1_simple_task():
    """示例 1: 使用便捷函数执行简单任务"""
    print("=" * 60)
    print("示例 1: 使用便捷函数 execute_task")
    print("=" * 60)

    try:
        result = execute_task(
            "给我在浏览器中看看 罗翔说刑法、一数、老师好我叫何同学 这3个哔哩哔哩up主的播放量最高的视频的播放量和发布日期",
            max_iterations=80,
        )
        print(f"任务结果: {result}")
    except Exception as e:
        print(f"错误: {e}")


def example_2_class_api():
    """示例 2: 使用 BaodouAI 类"""
    print("\n" + "=" * 60)
    print("示例 2: 使用 BaodouAI 类")
    print("=" * 60)

    try:
        ai = BaodouAI(
            api_key="your_api_key_here",  # 替换为你的 API Key
            base_url="https://api.example.com",  # 可选
            model_name="your_model_name",  # 可选
        )

        result = ai.execute(
            "打开浏览器并访问百度",
            max_iterations=20,
        )
        print(f"任务结果: {result}")
    except Exception as e:
        print(f"错误: {e}")


def example_3_with_callbacks():
    """示例 3: 使用回调函数"""
    print("\n" + "=" * 60)
    print("示例 3: 使用回调函数")
    print("=" * 60)

    try:
        ai = BaodouAI(api_key="your_api_key_here")

        def on_iteration(idx, info):
            """迭代回调"""
            print(f"[迭代 {idx}] 思考: {info.get('thinking', '')}")
            print(f"          操作: {info.get('action', '')} @ {info.get('coordinates', '')}")

        def on_transparent_enter():
            print("→ 进入透明模式")

        def on_transparent_exit():
            print("← 退出透明模式")

        result = ai.execute(
            "打开计算器",
            max_iterations=15,
            on_iteration=on_iteration,
            on_transparent_enter=on_transparent_enter,
            on_transparent_exit=on_transparent_exit,
        )
        print(f"任务结果: {result}")
    except Exception as e:
        print(f"错误: {e}")


def example_4_stop_task():
    """示例 4: 停止正在执行的任务"""
    print("\n" + "=" * 60)
    print("示例 4: 停止正在执行的任务")
    print("=" * 60)

    try:
        ai = BaodouAI(api_key="your_api_key_here")

        import threading

        def stop_after_delay():
            time.sleep(10)  # 10 秒后停止
            print("正在停止任务...")
            ai.stop()

        stop_thread = threading.Thread(target=stop_after_delay)
        stop_thread.start()

        result = ai.execute(
            "执行一个长时间任务",
            max_iterations=30,
        )
        print(f"任务结果: {result}")
    except Exception as e:
        print(f"错误: {e}")


if __name__ == "__main__":
    print("包豆电脑 API 使用示例\n")
    print("请将 'your_api_key_here' 替换为你的实际 API Key 后再运行示例\n")
    start_time = time.time()

    # 取消注释以下示例来运行
    example_1_simple_task()
    # example_2_class_api()
    # example_3_with_callbacks()
    # example_4_stop_task()

    end_time = time.time()
    print(f"\n总运行时间: {end_time - start_time:.2f} 秒")