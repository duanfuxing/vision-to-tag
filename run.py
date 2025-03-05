import runpy
import multiprocessing
import time

def worker():
    """子进程执行函数，循环运行目标模块"""
    while True:
        print(f"进程 {multiprocessing.current_process().name} 启动模块...")
        try:
            runpy.run_module('app.services.google_vision', run_name='__main__')
        except Exception as e:
            print(f"模块执行异常: {e}")
        time.sleep(1)  # 防止异常后频繁重启

if __name__ == '__main__':
    # 创建5个进程
    processes = []
    for i in range(5):
        p = multiprocessing.Process(target=worker, name=f'Process-{i+1}')
        processes.append(p)
        p.start()

    # 等待所有进程结束（理论上不会执行到这里）
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\n检测到中断信号，终止所有进程...")
        for p in processes:
            p.terminate()
