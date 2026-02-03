import asyncio
from datetime import datetime

from carrot.app.auction.models import Auction, AuctionStatus, Bid
from carrot.app.auction.repositories import AuctionRepository
from carrot.db.connection import db

from carrot.app.auction.exceptions import (
    NotAllowedActionError,
    BidTooLowError,
    AuctionAlreadyFinishedError
)

async def check_auction_active(auction: Auction) -> None:
    if auction.status != AuctionStatus.ACTIVE:
        raise NotAllowedActionError()
    if auction.end_at <= datetime.now():
        raise AuctionAlreadyFinishedError()
    
async def check_bid_request(auction: Auction, bidder_id: str, bid_price: int) -> None:
    if auction.product.owner_id == bidder_id:
        raise NotAllowedActionError()
    if bid_price <= auction.current_price:
        raise BidTooLowError()

async def check_and_finalize_auction() -> None:
    async with db.session_factory() as session:
        repository = AuctionRepository(session)
        now = datetime.now()
        result = await repository.check_and_finalize_auctions(now)
        
