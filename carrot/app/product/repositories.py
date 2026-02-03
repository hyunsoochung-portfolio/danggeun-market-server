import datetime
from typing import List

from sqlalchemy import select, or_, update
from sqlalchemy.orm import selectinload, contains_eager
from sqlalchemy.ext.asyncio import AsyncSession

from carrot.app.product.models import Product
from carrot.app.auction.models import Auction, AuctionStatus


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_post(self, product: Product) -> Product:
        self.session.add(product)
        await self.session.flush()
        await self.session.refresh(product)
        return product

    async def create_auction(self, auction: Auction) -> Auction:
        self.session.add(auction)
        await self.session.flush()
        await self.session.refresh(auction)
        return auction
    
    async def update_post(self, product: Product) -> Product:
        merged = await self.session.merge(product)
        await self.session.flush()
        await self.session.refresh(merged)
        return merged

    async def get_post_by_product_id(self, product_id: str, with_auction: bool = False) -> Product | None:
        query = select(Product).where(Product.id == product_id)

        if with_auction:
            query = query.options(selectinload(Product.auction))

        result = await self.session.execute(query)
        return result.scalars().one_or_none()

    async def get_posts_by_query(
        self,
        user_id: str | None,
        keyword: str | None,
        region_id: str | None,
        show_auction: bool = False,
    ) -> List[Product]:
        query = select(Product)

        # 1. 필터링 로직 추가: show_auction이 False이면 Auction이 없는 것만 가져옴
        if not show_auction:
            # Product와 Auction을 Outer Join 한 뒤, Auction 데이터가 없는 것(None)만 필터링
            query = (
                query.outerjoin(Product.auction)
                .where(Auction.id == None)
                .options(selectinload(Product.auction))
            )
        else:
            query = query.join(Product.auction).options(contains_eager(Product.auction))

        if user_id:
            query = query.where(Product.owner_id == user_id)

        if keyword:
            search_pattern = f"%{keyword}%"
            query = query.where(
                or_(
                    Product.title.ilike(search_pattern),
                    Product.content.ilike(search_pattern),
                )
            )

        if region_id:
            query = query.where(Product.region_id == region_id)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_posts_all(self, show_auction: bool = False) -> List[Product]:
        query = select(Product)

        if not show_auction:
            # 경매 상품 제외 (Auction ID가 없는 것만)
            query = (
                query.outerjoin(Product.auction)
                .where(Auction.id == None)
                .options(selectinload(Product.auction))
            )
        else:
            query = query.join(Product.auction).options(contains_eager(Product.auction))

        result = await self.session.execute(query)
        return result.scalars().all()

    async def remove_post(self, product: Product) -> None:
        await self.session.delete(product)
        await self.session.flush()

    async def check_and_finalize_auction(self, current_time: datetime):
        # 1. Auction 테이블 상태 먼저 종료
        auction_update = (
            update(Auction)
            .where(Auction.status == AuctionStatus.ACTIVE)
            .where(Auction.end_at <= current_time)
            .values(status=AuctionStatus.FINISHED)
        )
        
        # 2. Product 테이블 업데이트 (Auction이 FINISHED로 바뀐 것들을 대상으로)
        # 혹은 동일한 시간 조건을 Product 업데이트에도 적용
        product_update = (
            update(Product)
            .where(
                Product.id.in_(
                    select(Auction.product_id)
                    .where(Auction.end_at <= current_time)
                )
            )
            .values(is_sold=True)
        )

        await self.session.execute(auction_update)
        await self.session.execute(product_update)
        await self.session.commit()