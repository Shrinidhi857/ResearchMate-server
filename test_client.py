"""
WebSocket CLIENT to test the LaTeX Agent
This connects TO the server, it doesn't start a new server!
"""

import asyncio
import websockets
import json


async def test_latex_agent():
    """Test the LaTeX agent with a simple request"""
    
    # UPDATE THIS PORT if your server is running on 8001
    uri = "ws://localhost:8001/ws/test-client-123"
    
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✓ Connected to LaTeX Agent\n")
            
            # Receive welcome message
            response = await websocket.recv()
            data = json.loads(response)
            print(f"[SERVER] {data.get('content', 'Connected')}\n")
            
            # Send a document request
            user_request = "Create a simple research paper about artificial intelligence with an equation"
            print(f"[YOU] {user_request}\n")
            
            await websocket.send(json.dumps({
                "type": "USER_MESSAGE",
                "content": user_request
            }))
            
            # Listen for responses
            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=60.0)
                    data = json.loads(response)
                    message_type = data.get("type")
                    
                    print(f"[SERVER - {message_type}]")
                    
                    if message_type == "AGENT_THINKING":
                        print(f"  {data.get('content')}\n")
                    
                    elif message_type == "CODE_GENERATED":
                        code = data.get("content", "")
                        attempt = data.get("attempt", 1)
                        print(f"  Code generated (Attempt {attempt})")
                        print(f"  Preview: {code[:200]}...\n")
                        
                        # Auto-succeed for testing
                        print("  ✓ Simulating successful compilation\n")
                        await websocket.send(json.dumps({
                            "type": "EXECUTION_SUCCESS"
                        }))
                    
                    elif message_type == "COMPILATION_COMPLETE":
                        print(f"  ✓ {data.get('content')}\n")
                        print("="*60)
                        print("SUCCESS! Test completed.")
                        print("="*60)
                        break
                    
                    elif message_type == "MAX_ATTEMPTS_REACHED":
                        print(f"  ✗ {data.get('content')}\n")
                        break
                
                except asyncio.TimeoutError:
                    print("\n⚠ Timeout waiting for server")
                    break
    
    except websockets.exceptions.WebSocketException as e:
        print(f"\n✗ WebSocket error: {e}")
        print("\nMake sure the server is running:")
        print("  python agent-test.py")
    except ConnectionRefusedError:
        print("\n✗ Connection refused!")
        print("\nThe server is not running. Start it with:")
        print("  python agent-test.py")
    except Exception as e:
        print(f"\n✗ Error: {e}")


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║         LaTeX Agent WebSocket Test Client                   ║
╚══════════════════════════════════════════════════════════════╝

This is a CLIENT that connects to the server.
Make sure the server is running first!
    """)
    
    try:
        asyncio.run(test_latex_agent())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")