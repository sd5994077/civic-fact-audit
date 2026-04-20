from fastapi import APIRouter

from app.api.v1 import candidates, claims, compare, evaluations, scores, statements

router = APIRouter(prefix='/v1')
router.include_router(candidates.router, tags=['candidates'])
router.include_router(statements.router, tags=['statements'])
router.include_router(claims.router, tags=['claims'])
router.include_router(evaluations.router, tags=['evaluations'])
router.include_router(scores.router, tags=['scores'])
router.include_router(compare.router, tags=['compare'])
