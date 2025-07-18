"""
AI助手主控制器
整合上下文构建、LLM调用、工具调度和事件日志等模块，实现完整的对话处理流程
"""

from typing import Dict, Any, List, Optional
import uuid
import logging
import json
import os
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

# 导入Tavily客户端
try:
    from tavily import TavilyClient
except ImportError:
    logging.warning("Tavily客户端导入失败，搜索功能将不可用")

from .context_builder import ContextBuilder
from .llm_caller import OpenAILLMCaller
from .tool_invoker import ToolInvoker, get_weather, generate_ai_id, generate_frequency
from .event_logger import EventLogger
from app.services.chat_memory_integration import ChatMemoryIntegration

class AIAssistant:
    """主AI助手控制器，整合所有模块"""
    
    def __init__(self, model_name: str = "gpt-4o"):
        self.context_builder = ContextBuilder()
        self.llm_caller = OpenAILLMCaller(model_name)
        self.tool_invoker = ToolInvoker()
        self.event_logger = EventLogger()
        
        # 导入聊天服务
        from app.services.chat_service import ChatService
        self.chat_service = ChatService()
        
        # 导入聊天记忆集成服务
        self.chat_memory_integration = ChatMemoryIntegration()
        
        # 注册默认工具
        self._register_default_tools()
        
    async def close(self):
        """关闭所有资源"""
        try:
            # 关闭LLM调用器
            if hasattr(self, 'llm_caller'):
                await self.llm_caller.close()
                self.llm_caller = None
            
            # 关闭其他可能持有资源的对象
            if hasattr(self, 'chat_service'):
                self.chat_service = None
                
            if hasattr(self, 'chat_memory_integration'):
                self.chat_memory_integration = None
                
            if hasattr(self, 'tool_invoker'):
                self.tool_invoker = None
                
            if hasattr(self, 'context_builder'):
                self.context_builder = None
                
            if hasattr(self, 'event_logger'):
                self.event_logger = None
                
            logging.info("AIAssistant实例已关闭所有资源")
            
        except Exception as e:
            logging.error(f"关闭AIAssistant资源时出错: {str(e)}")
            # 继续抛出异常，让调用者知道出了问题
            raise
            
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    def _register_default_tools(self):
        """注册默认工具"""
        # 天气工具
        self.tool_invoker.register_tool(
            name="get_weather",
            func=get_weather,
            description="获取指定城市和日期的天气信息",
            parameters={
                "city": {
                    "type": "string",
                    "description": "城市名称，如北京、上海、新加坡等"
                },
                "date": {
                    "type": "string",
                    "description": "日期，如今天、明天、后天等",
                    "optional": True
                }
            }
        )
        
        # AI-ID生成工具
        self.tool_invoker.register_tool(
            name="generate_ai_id",
            func=generate_ai_id,
            description="生成唯一的AI-ID标识符",
            parameters={
                "name": {
                    "type": "string",
                    "description": "AI的名称（可选）",
                    "optional": True
                }
            }
        )
        
        # 频率编号生成工具
        self.tool_invoker.register_tool(
            name="generate_frequency",
            func=generate_frequency,
            description="基于AI-ID生成频率编号",
            parameters={
                "ai_id": {
                    "type": "string",
                    "description": "AI-ID标识符"
                },
                "personality_type": {
                    "type": "string",
                    "description": "人格类型代码，默认为P",
                    "optional": True
                },
                "ai_type": {
                    "type": "string",
                    "description": "AI类型代码，默认为A",
                    "optional": True
                }
            }
        )
    
    async def process_query(self, user_input: str, session_id: str = None, user_id: str = None, ai_id: str = None, image_data: str = None, file_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """处理用户查询的完整流程
        
        Args:
            user_input: 用户输入的文本
            session_id: 会话ID，如果不提供则自动生成
            user_id: 用户ID，如果不提供则自动生成
            ai_id: AI ID，如果不提供则自动生成
            image_data: 图片数据（Base64格式）
            file_data: 文件数据，包含类型、数据和元信息
        """
        # 导入超时处理模块
        import asyncio
        from asyncio import TimeoutError
        
        # 设置全局超时时间为25秒，以确保不超过前端的30秒超时限制
        try:
            return await asyncio.wait_for(self._process_query_internal(
                user_input, session_id, user_id, ai_id, image_data, file_data
            ), timeout=25.0)
        except TimeoutError:
            logging.error(f"处理查询超时: session_id={session_id}")
            return {
                "response": "抱歉，处理您的请求超时。这可能是由于数据库查询耗时过长。请尝试发送更简短的消息或稍后再试。",
                "session_id": session_id,
                "has_tool_calls": False,
                "tool_results": [],
                "error": "处理超时"
            }
        except Exception as e:
            logging.error(f"处理查询失败: {str(e)}")
            return {
                "response": f"处理您的请求时出错: {str(e)}",
                "session_id": session_id,
                "has_tool_calls": False,
                "tool_results": [],
                "error": str(e)
            }
            
    async def _process_query_internal(self, user_input: str, session_id: str = None, user_id: str = None, ai_id: str = None, image_data: str = None, file_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """处理用户查询的内部实现方法"""
        import time
        start_time = time.time()
        logging.info(f"开始处理查询: session_id={session_id}, user_id={user_id}, 输入长度={len(user_input)}字符")
        
        # 生成会话 ID 和其他标识符（如果未提供）
        session_id = session_id or str(uuid.uuid4())
        user_id = user_id or "user_" + str(uuid.uuid4())[:8]
        ai_id = ai_id or "ai_" + str(uuid.uuid4())[:8]
        
        # 设置上下文构建器的会话信息
        self.context_builder.session_id = session_id
        self.context_builder.user_id = user_id
        self.context_builder.ai_id = ai_id
        
        # 初始化结果变量
        result = None
        
        # 1. 记录用户输入和文件信息
        file_type = file_data.get('type') if file_data else None
        file_info = file_data.get('info') if file_data else None
        
        self.event_logger.log_user_input(
            session_id, user_id, ai_id, user_input, 
            file_type=file_type, file_info=file_info
        )
        
        # 保存用户输入到数据库（仅对非匿名用户）
        
        # 检查是否为匿名用户
        if user_id == "anonymous" or user_id.startswith("anonymous"):
            logging.info(f"匿名用户，跳过数据库保存用户消息: session_id={session_id}")
        else:
            logging.info(f"Saving user message for session {session_id}")
            # 使用await等待消息保存完成
            await self.chat_service.save_message(
                session_id=session_id,
                user_id=user_id,
                role=user_id,  # 用户角色就是用户ID
                content=user_input,
                content_type="text",
                metadata={"file_type": file_type} if file_type else None
            )
        
        # 更新或创建会话元数据（仅对非匿名用户）
        if user_id == "anonymous" or user_id.startswith("anonymous"):
            logging.info(f"匿名用户，跳过数据库更新会话元数据: session_id={session_id}")
        else:
            logging.info(f"Updating session metadata for session {session_id}")
            await self.chat_service.update_session(
                session_id=session_id,
                user_id=user_id,
                title=user_input[:30] + ("..." if len(user_input) > 30 else ""),  # 使用用户输入的前30个字符作为标题
                last_message=user_input,
                last_message_time=datetime.now().isoformat()
            )
        
        # 2. 构建初始上下文
        logging.debug(f"Building initial context with user input and file data")
        
        # 如果有图片数据，优先使用image_data
        # 如果没有image_data但有文件数据且类型为图片，使用file_data
        if not image_data and file_data and file_type == 'image':
            logging.debug("Using image data from file_data")
            image_data = file_data.get('data')
            
        # 更新上下文，包含图片数据和文件数据（如果有）
        self.context_builder.update_context_with_user_message(
            user_input=user_input, 
            image_data=image_data,
            file_data=file_data
        )
        
        # 3. 使用记忆增强上下文（如果不是匿名用户）
        if user_id != "anonymous" and not user_id.startswith("anonymous"):
            try:
                # 导入超时处理模块
                import asyncio
                from asyncio import TimeoutError
                
                # 获取记忆增强，添加3秒超时
                logging.info(f"开始获取记忆增强: user_id={user_id}, session_id={session_id}")
                memory_enhancement = await asyncio.wait_for(
                    self.chat_memory_integration.enhance_response_with_memories(
                        user_id=user_id,
                        user_message=user_input,
                        current_session_id=session_id
                    ),
                    timeout=3.0  # 3秒超时
                )
                
                enhanced_context = memory_enhancement.get("context_enhancement", "")
                if enhanced_context:
                    logging.info(f"成功获取记忆增强上下文: {len(enhanced_context)} 字符")
                    
                    # 在系统消息中添加记忆增强上下文
                    system_message = None
                    for msg in self.context_builder.messages:
                        if msg.get("role") == "system":
                            system_message = msg
                            break
                            
                    if system_message:
                        # 在系统消息中添加记忆增强
                        original_content = system_message.get("content", "")
                        system_message["content"] = f"{original_content}\n\n用户相关信息:\n{enhanced_context}"
                        logging.info("记忆增强已添加到系统消息")
            except TimeoutError:
                logging.warning(f"记忆增强超时，继续处理但不使用记忆增强: session_id={session_id}")
            except Exception as e:
                logging.error(f"获取记忆增强失败: {str(e)}")
        else:
            logging.info(f"匿名用户，跳过记忆增强: user_id={user_id}, session_id={session_id}")

        
        messages = self.context_builder.get_conversation_history()
        
        # 4. 第一次LLM调用（带工具定义）
        tool_definitions = self.tool_invoker.get_tool_definitions()
        logging.info(f"开始第一次LLM调用: session_id={session_id}, 消息数={len(messages)}")
        llm_start_time = time.time()
        first_response = await self.llm_caller.invoke(messages, tools=tool_definitions)
        llm_duration = time.time() - llm_start_time
        logging.info(f"完成第一次LLM调用: session_id={session_id}, 耗时={llm_duration:.2f}秒")
        self.event_logger.log_llm_call(session_id, user_id, ai_id, messages, first_response, 1)
        
        # 检查AI回答是否表示不确定或无法回答
        if not first_response.get("tool_calls"):
            # 如果没有工具调用，检查AI回答是否表示不确定
            initial_content = first_response.get("content", "").lower()
            
            # 检测AI是否表示不知道或无法回答
            uncertainty_phrases = [
                "我不知道", "无法提供", "没有这个信息", "无法回答", "不确定", 
                "没有足够的信息", "知识有限", "知识库中没有", "训练数据中没有",
                "知识库截止于", "信息可能过时", "无法获取实时信息", "无法搜索",
                "建议您查询", "建议您搜索", "建议您查找", "无法访问互联网",
                "抱歉", "sorry", "无法获取", "无法为您提供", "无法实时", "作为ai", "作为 ai",
                "实时信息", "最新信息", "实时数据", "实时查询", "实时获取",
                "天气应用程序", "气象网站", "搜索引擎"
            ]
            
            logging.debug(f"检查AI回答是否包含不确定性短语: {initial_content[:100]}...")
            
            # 检测是否包含不确定性短语
            matched_phrases = [phrase for phrase in uncertainty_phrases if phrase in initial_content]
            
            logging.debug(f"检测到的不确定性短语: {matched_phrases if matched_phrases else '无'}")
            
            # 如果AI表示不确定或无法回答，自动触发搜索
            if matched_phrases:
                logging.debug(f"AI表示不确定，检测到以下短语: {matched_phrases}")
                logging.info("AI表示不确定，自动触发搜索")
                
                # 提取搜索查询
                search_query = user_input
                # 如果消息太长，尝试提取关键部分
                if len(search_query) > 100:
                    search_query = search_query[:100]
                    
                logging.info(f"由于AI不确定，触发搜索: '{search_query}'")
                
                try:
                    # 导入Tavily客户端
                    from tavily import TavilyClient
                    
                    # 从环境变量获取API密钥
                    import os
                    api_key = os.getenv("TAVILY_API_KEY")
                    
                    if api_key:
                        # 创建Tavily客户端
                        client_tavily = TavilyClient(api_key=api_key)
                        
                        # 执行搜索
                        logging.debug(f"开始执行Tavily搜索，参数: query={search_query}, search_depth=basic, max_results=5")
                        search_result = client_tavily.search(
                            query=search_query,
                            search_depth="basic",
                            max_results=5,
                            include_answer=True
                        )
                        logging.debug("Tavily搜索成功完成")
                        
                        # 将搜索结果添加到消息中
                        if "answer" in search_result and search_result["answer"]:
                            logging.debug(f"搜索结果包含答案，长度: {len(search_result['answer'])}")
                            
                            # 添加搜索结果作为系统消息
                            search_message = {
                                "role": "system",
                                "content": f"我注意到你对这个问题不确定。根据最新的网络搜索结果，这是关于 '{search_query}' 的信息\n\n{search_result['answer']}\n\n请基于这些信息重新回答用户的问题。"
                            }
                            messages.append(search_message)
                            logging.info(f"已将搜索结果添加到对话中，准备重新生成回答")
                            
                            # 添加搜索结果链接作为参考
                            if "results" in search_result and search_result["results"]:
                                sources = "\n\n数据来源:\n"
                                for i, result in enumerate(search_result["results"][:3]):
                                    sources += f"- {result.get('title', '无标题')}: {result.get('url', '')}\n"
                                sources_message = {
                                    "role": "system",
                                    "content": f"{sources}\n请在回答中包含这些来源信息。"
                                }
                                messages.append(sources_message)
                            
                            # 重新调用LLM获取更新的回答
                            logging.info("使用搜索结果重新调用LLM获取回答")
                            llm_start_time = time.time()
                            first_response = await self.llm_caller.invoke(messages)
                            llm_duration = time.time() - llm_start_time
                            logging.info(f"完成搜索后的LLM调用: session_id={session_id}, 耗时={llm_duration:.2f}秒")
                            self.event_logger.log_llm_call(session_id, user_id, ai_id, messages, first_response, "search_enhanced")
                    else:
                        logging.error("未找到TAVILY_API_KEY环境变量，无法执行搜索")
                except Exception as e:
                    logging.error(f"Tavily搜索错误: {str(e)}")
        
        # 5. 检查是否有工具调用
        if first_response.get("tool_calls"):
            # 处理所有工具调用
            for tool_call in first_response["tool_calls"]:
                tool_name = tool_call["name"]
                tool_args = tool_call["arguments"]
                tool_call_id = tool_call.get("id", f"call_{int(time.time())}")
                
                # 6. 执行工具调用
                tool_result = self.tool_invoker.invoke_tool(tool_name, **tool_args)
                
                # 记录工具调用
                self.event_logger.log_tool_call(
                    session_id, user_id, ai_id,
                    tool_name, tool_args, tool_result
                )
                
                # 7. 更新上下文
                self.context_builder.update_context_with_tool_result(tool_name, tool_result, tool_call_id)
            
            # 8. 第二次LLM调用（不带工具定义）
            updated_messages = self.context_builder.get_conversation_history()
            logging.info(f"开始第二次LLM调用: session_id={session_id}, 消息数={len(updated_messages)}")
            llm_start_time = time.time()
            final_response = await self.llm_caller.invoke(updated_messages)
            llm_duration = time.time() - llm_start_time
            logging.info(f"完成第二次LLM调用: session_id={session_id}, 耗时={llm_duration:.2f}秒")
            self.event_logger.log_llm_call(session_id, user_id, ai_id, updated_messages, final_response, 2)
            
            # 9. 添加助手回复到上下文
            self.context_builder.add_assistant_message(final_response["content"])
            
            # 10. 记录最终响应
            self.event_logger.log_final_response(
                session_id, user_id, ai_id,
                final_response["content"], True
            )
            
            # 保存AI回复到数据库（仅对非匿名用户）
            
            # 检查是否为匿名用户
            if user_id == "anonymous" or user_id.startswith("anonymous"):
                logging.info(f"匿名用户，跳过数据库保存AI回复: session_id={session_id}")
            else:
                logging.info(f"Saving AI response for session {session_id}")
                # 使用await等待消息保存完成
                await self.chat_service.save_message(
                    session_id=session_id,
                    user_id=user_id,
                    role=f"{user_id}_aiR",  # AI回复的角色格式
                    content=final_response["content"],
                    content_type="text"
                )
            
            # 临时禁用会话元数据更新，避免数据库阻塞
            logging.info(f"临时跳过会话更新以避免阻塞: session_id={session_id}")
            # 如果需要重新启用会话更新，请使用await
            # await self.chat_service.update_session(
            #     session_id=session_id,
            #     user_id=user_id,
            #     last_message=final_response["content"][:50] + ("..." if len(final_response["content"]) > 50 else ""),
            #     last_message_time=datetime.now().isoformat()
            # )
            
            # 11. 保存日志
            log_file = self.event_logger.save_logs(session_id)
            
            # 记录总处理时间
            total_duration = time.time() - start_time
            logging.info(f"完成查询处理(有工具调用): session_id={session_id}, 总耗时={total_duration:.2f}秒")
            
            # 返回结果
            return {
                "response": final_response["content"],
                "session_id": session_id,
                "has_tool_calls": True,
                "tool_results": self.context_builder.tool_results,
                "log_file": log_file
            }
        else:
            # 如果没有工具调用，直接使用第一次响应
            # 添加助手回复到上下文
            self.context_builder.add_assistant_message(first_response["content"])
            
            # 记录最终响应
            self.event_logger.log_final_response(
                session_id, user_id, ai_id,
                first_response["content"], False
            )
            
            # 保存AI回复到数据库（仅对非匿名用户）
            
            # 检查是否为匿名用户
            if user_id == "anonymous" or user_id.startswith("anonymous"):
                logging.info(f"匿名用户，跳过数据库保存AI回复: session_id={session_id}")
            else:
                logging.info(f"Saving AI response for session {session_id}")
                # 使用await等待消息保存完成
                await self.chat_service.save_message(
                    session_id=session_id,
                    user_id=user_id,
                    role=f"{user_id}_aiR",  # AI回复的角色格式
                    content=first_response["content"],
                    content_type="text"
                )
            
            # 临时禁用会话元数据更新，避免数据库阻塞
            logging.info(f"临时跳过会话更新以避免阻塞: session_id={session_id}")
            # 如果需要重新启用会话更新，请使用await
            # await self.chat_service.update_session(
            #     session_id=session_id,
            #     user_id=user_id,
            #     last_message=first_response["content"][:50] + ("..." if len(first_response["content"]) > 50 else ""),
            #     last_message_time=datetime.now().isoformat()
            # )
            
            # 保存日志
            log_file = self.event_logger.save_logs(session_id)
            
            # 记录总处理时间
            total_duration = time.time() - start_time
            logging.info(f"完成查询处理(无工具调用): session_id={session_id}, 总耗时={total_duration:.2f}秒")
            
            # 返回结果
            return {
                "response": first_response["content"],
                "session_id": session_id,
                "has_tool_calls": False,
                "tool_results": [],
                "log_file": log_file
            }
    
    def get_conversation_history(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话历史"""
        return self.context_builder.get_conversation_history() if self.context_builder.session_id == session_id else []
    
    def get_session_logs(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话日志"""
        logs = self.event_logger.get_session_logs(session_id)
        return [log.to_dict() for log in logs]
    
    def clear_session(self, session_id: str) -> bool:
        """清除会话数据"""
        if self.context_builder.session_id == session_id:
            self.context_builder.clear_context()
            return True
        return False
