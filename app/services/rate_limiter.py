import time
import threading
from typing import Optional
from redis import Redis

class RateLimiter:
    _instance: Optional['RateLimiter'] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self, redis_client: Optional[Redis] = None):
        if not hasattr(self, '_initialized'):
            self.redis = redis_client or Redis(host='localhost', port=6379, db=0)
            
            # 令牌桶相关的 key
            self.token_bucket_key = "rate_limiter:token_bucket"
            self.request_count_key = "rate_limiter:request_count"
            self.last_reset_time_key = "rate_limiter:last_reset_time"
            
            # 限制配置
            self.max_requests = 2000  # 每分钟最大请求数
            self.max_tokens = 4_000_000  # 每分钟最大令牌数
            self.window_size = 60  # 时间窗口大小（秒）
            
            self._initialized = True
            
            # 初始化限流器状态
            self._init_state()

    def _init_state(self):
        """初始化或重置限流器状态"""
        now = time.time()
        if not self.redis.exists(self.last_reset_time_key):
            pipeline = self.redis.pipeline()
            pipeline.set(self.token_bucket_key, self.max_tokens)
            pipeline.set(self.request_count_key, 0)
            pipeline.set(self.last_reset_time_key, now)
            pipeline.execute()

    def _check_and_reset_window(self) -> None:
        """检查是否需要重置时间窗口"""
        now = time.time()
        last_reset_time = float(self.redis.get(self.last_reset_time_key) or now)
        
        if now - last_reset_time >= self.window_size:
            # 使用 Lua 脚本保证原子性
            reset_script = """
            local now = tonumber(ARGV[1])
            local last_reset = tonumber(redis.call('get', KEYS[1]))
            
            if (now - last_reset) >= 60 then
                redis.call('set', KEYS[2], ARGV[2])  -- reset token bucket
                redis.call('set', KEYS[3], '0')      -- reset request count
                redis.call('set', KEYS[1], now)      -- update last reset time
                return 1
            end
            return 0
            """
            
            self.redis.eval(
                reset_script,
                3,  # 3个键
                self.last_reset_time_key,
                self.token_bucket_key,
                self.request_count_key,
                now,
                self.max_tokens
            )

    def acquire(self, tokens: int) -> bool:
        """
        尝试获取令牌
        :param tokens: 需要的令牌数
        :return: 是否获取成功
        """
        if tokens <= 0:
            raise ValueError("令牌数必须大于0")
        if tokens > self.max_tokens:
            raise ValueError(f"请求的令牌数超过限制 ({self.max_tokens})")
            
        while True:
            self._check_and_reset_window()
            
            # 使用 Lua 脚本保证原子性
            acquire_script = """
            local current_tokens = tonumber(redis.call('get', KEYS[1]))
            local current_requests = tonumber(redis.call('get', KEYS[2]))
            local tokens_needed = tonumber(ARGV[1])
            local max_requests = tonumber(ARGV[2])
            
            if current_tokens >= tokens_needed and current_requests < max_requests then
                redis.call('decrby', KEYS[1], tokens_needed)
                redis.call('incr', KEYS[2])
                return 1
            end
            return 0
            """
            
            result = self.redis.eval(
                acquire_script,
                2,  # 2个键
                self.token_bucket_key,
                self.request_count_key,
                tokens,
                self.max_requests
            )
            
            if result == 1:
                return True
                
            # 获取当前状态用于日志
            current_tokens = int(self.redis.get(self.token_bucket_key) or 0)
            current_requests = int(self.redis.get(self.request_count_key) or 0)
            
            if current_requests >= self.max_requests:
                print(f"达到请求数限制 ({current_requests}/{self.max_requests})")
            if current_tokens < tokens:
                print(f"令牌不足 (需要: {tokens}, 当前: {current_tokens})")
                
            # 如果获取失败，等待一小段时间再试
            time.sleep(0.1)

    def get_stats(self):
        """获取当前限流统计信息"""
        pipeline = self.redis.pipeline()
        pipeline.get(self.token_bucket_key)
        pipeline.get(self.request_count_key)
        pipeline.get(self.last_reset_time_key)
        current_tokens, current_requests, last_reset_time = pipeline.execute()
        
        return {
            'current_tokens': int(current_tokens or 0),
            'current_requests': int(current_requests or 0),
            'remaining_tokens': max(0, self.max_tokens - int(current_tokens or 0)),
            'remaining_requests': max(0, self.max_requests - int(current_requests or 0)),
            'last_reset_time': float(last_reset_time or 0)
        }

    def increment_request(self) -> bool:
        """
        增加请求计数
        :return: 是否增加成功（是否超过限制）
        """
        self._check_and_reset_window()
        
        # 使用 Lua 脚本保证原子性
        increment_script = """
        local current_requests = tonumber(redis.call('get', KEYS[1]))
        local max_requests = tonumber(ARGV[1])
        
        if current_requests < max_requests then
            redis.call('incr', KEYS[1])
            return 1
        end
        return 0
        """
        
        result = self.redis.eval(
            increment_script,
            1,  # 1个键
            self.request_count_key,
            self.max_requests
        )
        
        success = bool(result)
        if not success:
            current_requests = int(self.redis.get(self.request_count_key) or 0)
            print(f"达到请求数限制 ({current_requests}/{self.max_requests})")
        
        return success

    def increment_tokens(self, tokens: int) -> bool:
        """
        增加token计数
        :param tokens: 需要增加的token数
        :return: 是否增加成功（是否超过限制）
        """
        if tokens <= 0:
            raise ValueError("token数必须大于0")
        if tokens > self.max_tokens:
            raise ValueError(f"请求的token数超过限制 ({self.max_tokens})")
            
        self._check_and_reset_window()
        
        # 使用 Lua 脚本保证原子性
        increment_script = """
        local current_tokens = tonumber(redis.call('get', KEYS[1]))
        local tokens_to_add = tonumber(ARGV[1])
        local max_tokens = tonumber(ARGV[2])
        
        if (current_tokens + tokens_to_add) <= max_tokens then
            redis.call('incrby', KEYS[1], tokens_to_add)
            return 1
        end
        return 0
        """
        
        result = self.redis.eval(
            increment_script,
            1,  # 1个键
            self.token_bucket_key,
            tokens,
            self.max_tokens
        )
        
        success = bool(result)
        if not success:
            current_tokens = int(self.redis.get(self.token_bucket_key) or 0)
            print(f"达到token限制 (当前: {current_tokens}, 尝试增加: {tokens}, 最大: {self.max_tokens})")
        
        return success

# 测试代码
if __name__ == "__main__":
    import concurrent.futures
    
    redis_client = Redis(host='localhost', port=6379, db=0)
    limiter = RateLimiter(redis_client)
    
    def test_increment():
        try:
            # 测试请求计数
            req_success = limiter.increment_request()
            print(f"增加请求计数: {'成功' if req_success else '失败'}")
            
            # 测试token计数
            token_success = limiter.increment_tokens(1000)
            print(f"增加1000个token: {'成功' if token_success else '失败'}")
            
            # 打印当前状态
            print("当前状态:", limiter.get_stats())
            
        except Exception as e:
            print(f"错误: {e}")
    
    # 并发测试
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        print("测试场景1: 并发增加请求计数和token")
        futures = [executor.submit(test_increment) for _ in range(2100)]
        concurrent.futures.wait(futures)
        
        print("\n最终状态:", limiter.get_stats())