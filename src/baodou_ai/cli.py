"""
CoView 同窗 CLI 命令行工具

通过终端直接执行自动化任务。

使用方法:
    coview-cli "打开浏览器" --api-key YOUR_KEY
    coview-cli "打开记事本" --api-key YOUR_KEY --max-iterations 10
"""

import argparse
import sys

from baodou_ai.api import CoViewAI


def main():
    parser = argparse.ArgumentParser(
        description="CoView 同窗 - AI 智能控制系统命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  coview-cli "打开浏览器" --api-key YOUR_KEY
  coview-cli "打开记事本并输入Hello" --api-key YOUR_KEY --max-iterations 20
  coview-cli "关闭窗口" --api-key YOUR_KEY --base-url https://api.example.com
        """,
    )

    parser.add_argument(
        "task",
        type=str,
        help="要执行的任务描述，例如：'打开浏览器'、'打开记事本'",
    )

    parser.add_argument(
        "--api-key",
        "-k",
        type=str,
        help="API 密钥（如果配置文件中已设置可省略）",
    )

    parser.add_argument(
        "--base-url",
        "-u",
        type=str,
        help="API 基础地址（可选）",
    )

    parser.add_argument(
        "--model-name",
        "-m",
        type=str,
        help="模型名称（可选）",
    )

    parser.add_argument(
        "--max-iterations",
        "-i",
        type=int,
        help="最大迭代次数（可选，默认使用配置文件中的值）",
    )

    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version="CoView CLI v2.0.0",
        help="显示版本信息",
    )

    args = parser.parse_args()

    try:
        print("=" * 60)
        print("CoView 同窗 - AI 智能控制系统")
        print("=" * 60)
        print(f"任务: {args.task}")
        print()

        ai = CoViewAI(
            api_key=args.api_key,
            base_url=args.base_url,
            model_name=args.model_name,
        )

        stream_state = {
            "current_iteration": None,
            "line_open": False,
        }

        def on_model_stream(iteration: int, chunk: str) -> None:
            if stream_state["current_iteration"] != iteration:
                if stream_state["line_open"]:
                    print()
                print(f"[第 {iteration + 1} 轮模型输出] ", end="", flush=True)
                stream_state["current_iteration"] = iteration
                stream_state["line_open"] = True

            print(chunk, end="", flush=True)

        def on_iteration(idx, info) -> None:
            if stream_state["line_open"]:
                print()
                stream_state["line_open"] = False
            print(f"[迭代 {idx + 1}] {info.get('thinking', '')}")

        result = ai.execute(
            args.task,
            max_iterations=args.max_iterations,
            on_iteration=on_iteration,
            on_model_stream=on_model_stream,
        )

        if stream_state["line_open"]:
            print()

        print()
        print("=" * 60)
        print("执行完成！")
        print("=" * 60)
        print(f"结果: {result}")

        return 0

    except KeyboardInterrupt:
        print("\n\n用户中断执行")
        return 130
    except Exception as e:
        print(f"\n\n错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
