# TODO-5: Claude Code Integration

## Objective
Create a robust integration with Claude Code that supports both CLI subprocess execution and Python SDK integration, handling response streaming, session state, timeout handling, and output parsing while maintaining security and reliability.

## Integration Architecture

### Component Overview
```
Claude Integration Layer
├── SDK Integration (Python SDK - Default)
│   ├── Async SDK Client
│   ├── Streaming Support
│   ├── Authentication Manager
│   └── Tool Execution Monitoring
├── CLI Integration (Legacy subprocess)
│   ├── Process Manager (Subprocess handling)
│   ├── Output Parser (JSON/Stream parsing)
│   └── Timeout Handler (Prevent hanging)
├── Session Manager (State persistence)
├── Response Streamer (Real-time updates)
├── Cost Calculator (Usage tracking)
└── Tool Monitor (Track Claude's actions)
```

## Core Implementation

### Integration Modes

The bot supports two integration modes with Claude:

#### SDK Integration (Default - Recommended)
- Uses the Claude Code Python SDK for direct API integration
- Better performance with native async support
- Reliable streaming and error handling
- Can use existing Claude CLI authentication or direct API key
- Implementation in `src/claude/sdk_integration.py`

#### CLI Integration (Legacy)
- Uses Claude Code CLI as a subprocess
- Requires Claude CLI installation and authentication
- Legacy mode for compatibility
- Implementation in `src/claude/integration.py`

### Claude SDK Manager
```python
# src/claude/sdk_integration.py
"""
Claude Code Python SDK integration

Features:
- Native async support
- Streaming responses
- Direct API integration
- CLI authentication support
"""

import asyncio
from typing import AsyncIterator, Optional, Dict, Any
from claude_agent_sdk import query, ClaudeAgentOptions

@dataclass
class ClaudeResponse:
    """Response from Claude Code SDK"""
    content: str
    session_id: str
    cost: float
    duration_ms: int
    num_turns: int
    is_error: bool = False
    error_type: Optional[str] = None
    tools_used: List[Dict[str, Any]] = field(default_factory=list)

class ClaudeSDKManager:
    """Manage Claude Code SDK integration"""
    
    def __init__(self, config: Settings):
        self.config = config
        self.options = ClaudeAgentOptions(
            api_key=config.anthropic_api_key_str,
            timeout=config.claude_timeout_seconds,
            working_directory=config.approved_directory
        )
        
    async def execute_query(
        self,
        prompt: str,
        working_directory: Path,
        session_id: Optional[str] = None,
        stream_callback: Optional[Callable] = None
    ) -> ClaudeResponse:
        """Execute Claude query using SDK"""
        
        try:
            # Configure options for this query
            options = self.options.copy()
            options.working_directory = str(working_directory)
            
            # Execute with streaming
            async for update in query(prompt, options):
                if stream_callback:
                    await stream_callback(update)
                    
            # Return final response
            return self._format_response(update, session_id)
            
        except Exception as e:
            return ClaudeResponse(
                content=f"Error: {str(e)}",
                session_id=session_id or "unknown",
                cost=0.0,
                duration_ms=0,
                num_turns=0,
                is_error=True,
                error_type=type(e).__name__
            )
```

### Claude Process Manager (CLI Mode)
```python
# src/claude/integration.py
"""
Claude Code subprocess management

Features:
- Async subprocess execution
- Stream handling
- Timeout management
- Error recovery
"""

import asyncio
import json
from asyncio.subprocess import Process
from dataclasses import dataclass
from typing import Optional, Callable, AsyncIterator, Dict, Any
from datetime import datetime
import uuid

@dataclass
class ClaudeResponse:
    """Response from Claude Code"""
    content: str
    session_id: str
    cost: float
    duration_ms: int
    num_turns: int
    is_error: bool = False
    error_type: Optional[str] = None
    tools_used: List[Dict[str, Any]] = None

@dataclass
class StreamUpdate:
    """Streaming update from Claude"""
    type: str  # 'assistant', 'user', 'system', 'result'
    content: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    metadata: Optional[Dict] = None

class ClaudeProcessManager:
    """Manage Claude Code subprocess execution"""
    
    def __init__(self, config: Settings):
        self.config = config
        self.active_processes: Dict[str, Process] = {}
        
    async def execute_command(
        self,
        prompt: str,
        working_directory: Path,
        session_id: Optional[str] = None,
        continue_session: bool = False,
        stream_callback: Optional[Callable[[StreamUpdate], None]] = None
    ) -> ClaudeResponse:
        """Execute Claude Code command"""
        
        # Build command
        cmd = self._build_command(prompt, session_id, continue_session)
        
        # Create process ID for tracking
        process_id = str(uuid.uuid4())
        
        try:
            # Start process
            process = await self._start_process(cmd, working_directory)
            self.active_processes[process_id] = process
            
            # Handle output with timeout
            result = await asyncio.wait_for(
                self._handle_process_output(process, stream_callback),
                timeout=self.config.claude_timeout_seconds
            )
            
            return result
            
        except asyncio.TimeoutError:
            # Kill process on timeout
            if process_id in self.active_processes:
                self.active_processes[process_id].kill()
                await self.active_processes[process_id].wait()
            
            raise ClaudeTimeoutError(
                f"Claude Code timed out after {self.config.claude_timeout_seconds}s"
            )
            
        finally:
            # Clean up
            if process_id in self.active_processes:
                del self.active_processes[process_id]
    
    def _build_command(
        self, 
        prompt: str, 
        session_id: Optional[str], 
        continue_session: bool
    ) -> List[str]:
        """Build Claude Code command with arguments"""
        cmd = ['claude']
        
        if continue_session and not prompt:
            # Continue without new prompt
            cmd.extend(['--continue'])
        else:
            # New prompt or continue with prompt
            if continue_session:
                cmd.extend(['--continue', prompt])
            else:
                cmd.extend(['-p', prompt])
                
                if session_id:
                    cmd.extend(['--resume', session_id])
        
        # Always use streaming JSON for real-time updates
        cmd.extend(['--output-format', 'stream-json'])
        
        # Add safety limits
        cmd.extend(['--max-turns', str(self.config.claude_max_turns)])
        
        # Add allowed tools if configured
        if hasattr(self.config, 'allowed_tools'):
            cmd.extend(['--allowedTools', ','.join(self.config.allowed_tools)])
        
        return cmd
    
    async def _start_process(self, cmd: List[str], cwd: Path) -> Process:
        """Start Claude Code subprocess"""
        return await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            # Limit memory usage
            limit=1024 * 1024 * 512  # 512MB
        )
    
    async def _handle_process_output(
        self, 
        process: Process,
        stream_callback: Optional[Callable]
    ) -> ClaudeResponse:
        """Handle streaming output from Claude Code"""
        messages = []
        result = None
        
        async for line in self._read_stream(process.stdout):
            try:
                msg = json.loads(line)
                messages.append(msg)
                
                # Create stream update
                update = self._parse_stream_message(msg)
                if update and stream_callback:
                    await stream_callback(update)
                
                # Check for final result
                if msg.get('type') == 'result':
                    result = msg
                    
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON: {line}")
                continue
        
        # Wait for process to complete
        return_code = await process.wait()
        
        if return_code != 0:
            stderr = await process.stderr.read()
            raise ClaudeProcessError(
                f"Claude Code exited with code {return_code}: {stderr.decode()}"
            )
        
        if not result:
            raise ClaudeParsingError("No result message received from Claude Code")
        
        return self._parse_result(result, messages)
    
    async def _read_stream(self, stream) -> AsyncIterator[str]:
        """Read lines from stream"""
        while True:
            line = await stream.readline()
            if not line:
                break
            yield line.decode('utf-8').strip()
    
    def _parse_stream_message(self, msg: Dict) -> Optional[StreamUpdate]:
        """Parse streaming message into update"""
        msg_type = msg.get('type')
        
        if msg_type == 'assistant':
            # Extract content and tool calls
            message = msg.get('message', {})
            content_blocks = message.get('content', [])
            
            # Get text content
            text_content = []
            tool_calls = []
            
            for block in content_blocks:
                if block.get('type') == 'text':
                    text_content.append(block.get('text', ''))
                elif block.get('type') == 'tool_use':
                    tool_calls.append({
                        'name': block.get('name'),
                        'input': block.get('input', {})
                    })
            
            return StreamUpdate(
                type='assistant',
                content='\n'.join(text_content) if text_content else None,
                tool_calls=tool_calls if tool_calls else None
            )
            
        elif msg_type == 'system' and msg.get('subtype') == 'init':
            # Initial system message with available tools
            return StreamUpdate(
                type='system',
                metadata={
                    'tools': msg.get('tools', []),
                    'mcp_servers': msg.get('mcp_servers', [])
                }
            )
        
        return None
    
    def _parse_result(self, result: Dict, messages: List[Dict]) -> ClaudeResponse:
        """Parse final result message"""
        # Extract tools used from messages
        tools_used = []
        for msg in messages:
            if msg.get('type') == 'assistant':
                message = msg.get('message', {})
                for block in message.get('content', []):
                    if block.get('type') == 'tool_use':
                        tools_used.append({
                            'name': block.get('name'),
                            'timestamp': msg.get('timestamp')
                        })
        
        return ClaudeResponse(
            content=result.get('result', ''),
            session_id=result.get('session_id', ''),
            cost=result.get('cost_usd', 0.0),
            duration_ms=result.get('duration_ms', 0),
            num_turns=result.get('num_turns', 0),
            is_error=result.get('is_error', False),
            error_type=result.get('subtype') if result.get('is_error') else None,
            tools_used=tools_used
        )
```

### Session State Manager
```python
# src/claude/session.py
"""
Claude Code session management

Features:
- Session state tracking
- Multi-project support
- Session persistence
- Cleanup policies
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from pathlib import Path

@dataclass
class ClaudeSession:
    """Claude Code session state"""
    session_id: str
    user_id: int
    project_path: Path
    created_at: datetime
    last_used: datetime
    total_cost: float = 0.0
    total_turns: int = 0
    message_count: int = 0
    tools_used: List[str] = field(default_factory=list)
    
    def is_expired(self, timeout_hours: int) -> bool:
        """Check if session has expired"""
        age = datetime.utcnow() - self.last_used
        return age > timedelta(hours=timeout_hours)
    
    def update_usage(self, response: ClaudeResponse):
        """Update session with usage from response"""
        self.last_used = datetime.utcnow()
        self.total_cost += response.cost
        self.total_turns += response.num_turns
        self.message_count += 1
        
        # Track unique tools
        if response.tools_used:
            for tool in response.tools_used:
                tool_name = tool.get('name')
                if tool_name and tool_name not in self.tools_used:
                    self.tools_used.append(tool_name)

class SessionManager:
    """Manage Claude Code sessions"""
    
    def __init__(self, config: Settings, storage: 'SessionStorage'):
        self.config = config
        self.storage = storage
        self.active_sessions: Dict[str, ClaudeSession] = {}
        
    async def get_or_create_session(
        self, 
        user_id: int, 
        project_path: Path,
        session_id: Optional[str] = None
    ) -> ClaudeSession:
        """Get existing session or create new one"""
        
        # Check for existing session
        if session_id and session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            if not session.is_expired(self.config.session_timeout_hours):
                return session
        
        # Try to load from storage
        if session_id:
            session = await self.storage.load_session(session_id)
            if session and not session.is_expired(self.config.session_timeout_hours):
                self.active_sessions[session_id] = session
                return session
        
        # Check user session limit
        user_sessions = await self._get_user_sessions(user_id)
        if len(user_sessions) >= self.config.max_sessions_per_user:
            # Remove oldest session
            oldest = min(user_sessions, key=lambda s: s.last_used)
            await self.remove_session(oldest.session_id)
        
        # Create new session
        new_session = ClaudeSession(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            project_path=project_path,
            created_at=datetime.utcnow(),
            last_used=datetime.utcnow()
        )
        
        # Save to storage
        await self.storage.save_session(new_session)
        self.active_sessions[new_session.session_id] = new_session
        
        return new_session
    
    async def update_session(self, session_id: str, response: ClaudeResponse):
        """Update session with response data"""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            session.update_usage(response)
            
            # Persist to storage
            await self.storage.save_session(session)
    
    async def remove_session(self, session_id: str):
        """Remove session"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        
        await self.storage.delete_session(session_id)
    
    async def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        all_sessions = await self.storage.get_all_sessions()
        
        for session in all_sessions:
            if session.is_expired(self.config.session_timeout_hours):
                await self.remove_session(session.session_id)
    
    async def _get_user_sessions(self, user_id: int) -> List[ClaudeSession]:
        """Get all sessions for a user"""
        return await self.storage.get_user_sessions(user_id)
```

### Output Parser
```python
# src/claude/parser.py
"""
Parse Claude Code output formats

Features:
- JSON parsing
- Stream parsing
- Error detection
- Tool extraction
"""

class OutputParser:
    """Parse various Claude Code output formats"""
    
    @staticmethod
    def parse_json_output(output: str) -> Dict[str, Any]:
        """Parse single JSON output"""
        try:
            return json.loads(output)
        except json.JSONDecodeError as e:
            raise ClaudeParsingError(f"Failed to parse JSON output: {e}")
    
    @staticmethod
    def parse_stream_json(lines: List[str]) -> List[Dict[str, Any]]:
        """Parse streaming JSON output"""
        messages = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            try:
                msg = json.loads(line)
                messages.append(msg)
            except json.JSONDecodeError:
                logger.warning(f"Skipping invalid JSON line: {line}")
                continue
        
        return messages
    
    @staticmethod
    def extract_code_blocks(content: str) -> List[Dict[str, str]]:
        """Extract code blocks from response"""
        code_blocks = []
        pattern = r'```(\w+)?\n(.*?)```'
        
        for match in re.finditer(pattern, content, re.DOTALL):
            language = match.group(1) or 'text'
            code = match.group(2).strip()
            
            code_blocks.append({
                'language': language,
                'code': code
            })
        
        return code_blocks
    
    @staticmethod
    def extract_file_operations(messages: List[Dict]) -> List[Dict[str, Any]]:
        """Extract file operations from tool calls"""
        file_ops = []
        
        for msg in messages:
            if msg.get('type') != 'assistant':
                continue
                
            message = msg.get('message', {})
            for block in message.get('content', []):
                if block.get('type') != 'tool_use':
                    continue
                
                tool_name = block.get('name', '')
                tool_input = block.get('input', {})
                
                # Check for file-related tools
                if tool_name in ['create_file', 'edit_file', 'read_file']:
                    file_ops.append({
                        'operation': tool_name,
                        'path': tool_input.get('path'),
                        'content': tool_input.get('content'),
                        'timestamp': msg.get('timestamp')
                    })
        
        return file_ops
```

### Tool Monitor
```python
# src/claude/monitor.py
"""
Monitor Claude's tool usage

Features:
- Track tool calls
- Security validation
- Usage analytics
"""

class ToolMonitor:
    """Monitor and validate Claude's tool usage"""
    
    def __init__(self, config: Settings, security_validator: SecurityValidator):
        self.config = config
        self.security_validator = security_validator
        self.tool_usage: Dict[str, int] = defaultdict(int)
        
    async def validate_tool_call(
        self, 
        tool_name: str, 
        tool_input: Dict[str, Any],
        working_directory: Path
    ) -> Tuple[bool, Optional[str]]:
        """Validate tool call before execution"""
        
        # Check if tool is allowed
        if hasattr(self.config, 'allowed_tools'):
            if tool_name not in self.config.allowed_tools:
                return False, f"Tool not allowed: {tool_name}"
        
        # Validate file operations
        if tool_name in ['create_file', 'edit_file', 'read_file']:
            file_path = tool_input.get('path')
            if not file_path:
                return False, "File path required"
            
            # Validate path security
            valid, resolved_path, error = self.security_validator.validate_path(
                file_path, 
                working_directory
            )
            
            if not valid:
                return False, error
        
        # Track usage
        self.tool_usage[tool_name] += 1
        
        return True, None
    
    def get_tool_stats(self) -> Dict[str, Any]:
        """Get tool usage statistics"""
        return {
            'total_calls': sum(self.tool_usage.values()),
            'by_tool': dict(self.tool_usage),
            'unique_tools': len(self.tool_usage)
        }
```

### Integration Facade
```python
# src/claude/facade.py
"""
High-level Claude Code integration facade

Provides simple interface for bot handlers
"""

class ClaudeIntegration:
    """Main integration point for Claude Code"""
    
    def __init__(
        self,
        config: Settings,
        process_manager: ClaudeProcessManager,
        session_manager: SessionManager,
        tool_monitor: ToolMonitor
    ):
        self.config = config
        self.process_manager = process_manager
        self.session_manager = session_manager
        self.tool_monitor = tool_monitor
        
    async def run_command(
        self,
        prompt: str,
        working_directory: Path,
        user_id: int,
        session_id: Optional[str] = None,
        on_stream: Optional[Callable[[StreamUpdate], None]] = None
    ) -> ClaudeResponse:
        """Run Claude Code command with full integration"""
        
        # Get or create session
        session = await self.session_manager.get_or_create_session(
            user_id,
            working_directory,
            session_id
        )
        
        # Track streaming updates
        tools_validated = True
        
        async def stream_handler(update: StreamUpdate):
            # Validate tool calls
            if update.tool_calls:
                for tool_call in update.tool_calls:
                    valid, error = await self.tool_monitor.validate_tool_call(
                        tool_call['name'],
                        tool_call.get('input', {}),
                        working_directory
                    )
                    
                    if not valid:
                        tools_validated = False
                        logger.error(f"Tool validation failed: {error}")
            
            # Pass to caller's handler
            if on_stream:
                await on_stream(update)
        
        # Execute command
        response = await self.process_manager.execute_command(
            prompt=prompt,
            working_directory=working_directory,
            session_id=session.session_id,
            continue_session=bool(session_id),
            stream_callback=stream_handler
        )
        
        # Update session
        await self.session_manager.update_session(session.session_id, response)
        
        # Set session ID in response
        response.session_id = session.session_id
        
        return response
    
    async def continue_session(
        self,
        user_id: int,
        working_directory: Path,
        prompt: Optional[str] = None
    ) -> Optional[ClaudeResponse]:
        """Continue the most recent session"""
        
        # Get user's sessions
        sessions = await self.session_manager._get_user_sessions(user_id)
        
        # Find most recent session in this directory
        matching_sessions = [
            s for s in sessions 
            if s.project_path == working_directory
        ]
        
        if not matching_sessions:
            return None
        
        # Get most recent
        latest_session = max(matching_sessions, key=lambda s: s.last_used)
        
        # Continue session
        return await self.run_command(
            prompt=prompt or "",
            working_directory=working_directory,
            user_id=user_id,
            session_id=latest_session.session_id
        )
    
    async def get_session_info(
        self, 
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get session information"""
        session = self.active_sessions.get(session_id)
        
        if not session:
            session = await self.storage.load_session(session_id)
        
        if session:
            return {
                'session_id': session.session_id,
                'project': str(session.project_path),
                'created': session.created_at.isoformat(),
                'last_used': session.last_used.isoformat(),
                'cost': session.total_cost,
                'turns': session.total_turns,
                'messages': session.message_count,
                'tools_used': session.tools_used
            }
        
        return None
```

## Error Handling

### Custom Exceptions
```python
# src/claude/exceptions.py
"""
Claude-specific exceptions
"""

class ClaudeError(Exception):
    """Base Claude error"""
    pass

class ClaudeTimeoutError(ClaudeError):
    """Operation timed out"""
    pass

class ClaudeProcessError(ClaudeError):
    """Process execution failed"""
    pass

class ClaudeParsingError(ClaudeError):
    """Failed to parse output"""
    pass

class ClaudeSessionError(ClaudeError):
    """Session management error"""
    pass
```

## Testing

### Integration Tests
```python
# tests/test_claude_integration.py
"""
Test Claude Code integration
"""

@pytest.fixture
async def mock_claude_process():
    """Mock Claude Code process"""
    # Return mock process that outputs test JSON
    pass

async def test_execute_command_success():
    """Test successful command execution"""
    
async def test_execute_command_timeout():
    """Test timeout handling"""
    
async def test_stream_parsing():
    """Test streaming JSON parsing"""
    
async def test_session_management():
    """Test session creation and persistence"""
    
async def test_tool_validation():
    """Test tool call validation"""
    
async def test_cost_tracking():
    """Test cost accumulation"""
```

## Configuration

### Claude-specific Settings
```python
# Additional settings for Claude integration
claude_binary_path: str = "claude"  # Path to Claude CLI
claude_allowed_tools: List[str] = [
    "create_file",
    "edit_file", 
    "read_file",
    "bash"
]
claude_disallowed_tools: List[str] = [
    "git commit",
    "git push"
]
claude_system_prompt_append: Optional[str] = None
claude_mcp_enabled: bool = False
claude_mcp_config: Optional[Dict] = None
```

## Success Criteria

- [ ] Claude Code subprocess executes successfully
- [ ] Streaming updates work in real-time
- [ ] Session state persists across commands
- [ ] Timeouts are properly handled
- [ ] Output parsing handles all formats
- [ ] Tool usage is tracked and validated
- [ ] Cost tracking accumulates correctly
- [ ] Sessions expire and cleanup works
- [ ] Error handling provides useful feedback
- [ ] Integration tests pass
- [ ] Memory usage stays within limits
- [ ] Concurrent sessions work properly