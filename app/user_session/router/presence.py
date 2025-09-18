from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict
import json

from app.user_session.crud.redis_presence import add_presence, remove_presence, get_presence

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter()
room_connections: Dict[str, set] = {}
connection_session: Dict[WebSocket, tuple] = {}

@router.websocket("/ws/presence/{roomId}")
async def ws_presence(websocket: WebSocket, roomId: str):
    from app.database import AsyncSessionLocal
    db = AsyncSessionLocal()
    try:
        await websocket.accept()
        clientIp = websocket.client.host
        logger.info(f"[Presence WS] 새 연결 roomId={roomId} clientIp={clientIp}")

        if roomId not in room_connections:
            room_connections[roomId] = set()
        room_connections[roomId].add(websocket)

        while True:
            message = await websocket.receive_text()
            logger.debug(f"[Presence WS] message 수신: {message}")
            data = json.loads(message)

            if data['type'] == 'join':
                userId = data['user']['userId']
                sessionId = data['user']['sessionId']
                nickname = data['user'].get('nickname', "")
                userAgentLabel = "그룹원"
                userData = {
                    "userId": userId,
                    "nickname": nickname,
                    "ipAddress": clientIp,
                    "userAgent": userAgentLabel
                }
                logger.debug(f"[JOIN] add_presence에 전달 userData: {userData}")
                await add_presence(roomId, userId, sessionId, userData)
                connection_session[websocket] = (userId, sessionId)

            elif data['type'] == 'leave':
                info = connection_session.pop(websocket, None)
                if info:
                    userId, sessionId = info
                else:
                    userId = data.get('userId') or data.get('user', {}).get('userId')
                    sessionId = data.get('sessionId')
                logger.info(f"[LEAVE] userId={userId} sessionId={sessionId}")
                await remove_presence(roomId, userId, sessionId)
                room_connections[roomId].discard(websocket)

            ids, users = await get_presence(roomId)
            logger.debug(f"[BROADCAST] ids={ids} users={users}")
            for ws in list(room_connections[roomId]):
                try:
                    await ws.send_text(json.dumps({
                        "type": "presence_update",
                        "count": len(ids),
                        "users": users
                    }))
                    logger.debug(f"[BROADCAST] 전송 ▶ count={len(ids)} users(example)={users[:1]}")
                except Exception:
                    room_connections[roomId].discard(ws)

    except WebSocketDisconnect:
        info = connection_session.pop(websocket, None)
        if info:
            userId, sessionId = info
            await remove_presence(roomId, userId, sessionId)
        room_connections[roomId].discard(websocket)
        ids, users = await get_presence(roomId)
        logger.warning(f"[WS DISCONNECT] 강제퇴장 ids={ids} users(example)={users[:1]}")
        for ws in list(room_connections[roomId]):
            try:
                await ws.send_text(json.dumps({
                    "type": "presence_update",
                    "count": len(ids),
                    "users": users
                }))
            except Exception:
                room_connections[roomId].discard(ws)
    except Exception as e:
        logger.error(f"[WS ERROR] {e}")
        connection_session.pop(websocket, None)
        room_connections[roomId].discard(websocket)
        #FastAPI WebSocket 엔드포인트에서 특정 방(roomId) 내 사용자들의 실시간 입장/퇴장(presence) 관리를 담당하는 메인 로직
        #room_connections : 각 방에 접속한 실시간 클라이언트(WebSocket)를 집합으로 관리.
        #connection_session : 각 웹소켓과 userId/sessionId를 연결해서 상태 추적 및 관리.
        #add_presence / remove_presence / get_presence : Redis에 실시간 상태 기록, 삭제, 조회 기능으로 사용자 활동을 기록/반영.
        #브로드캐스트 방에 연결된 전체 사용자들에게 실시간 상태 변화(presence_update)를 전파.

