import json
import logging
import os

import tornado.ioloop
import tornado.web
import tornado.websocket

from src.beer.beer import Beer
from src.beer.beerdb import BeerDB
from src.helpers.exceptions import UnValidVolumeError, NotFoundException
from src.helpers.logger import init_logger
from src.patterns.observer import Observer


class BeersHandler(tornado.web.RequestHandler):
    """
    HTTP handler for the /api/beers endpoints.
    """

    async def get(self):
        """
        Get Beers: GET method Handler that sends a paginated and filtered list of beers
        :return: Returns the corresponding page from the full list of beers
        """
        page_number = self.get_query_argument('page', '1')
        page_size = self.get_query_argument('page_size', '50')
        beer_type = self.get_query_argument('type', None)
        if beer_type is None:
            result = await beers.find(page_number=int(page_number), page_size=int(page_size))
        else:
            result = await beers.find_by_type(beer_type, page_number=int(page_number), page_size=int(page_size))
        self.write({'beers': result})

    async def post(self, _=None):
        """
        Post Beer: POST method Handler that adds new beers to the collection and returns the added beer after
        determining the served beer type
        :param _: None
        :return: The created beer
        """
        try:
            beer = json.loads(self.request.body)
            beer_id = next(beer_ids)
            new_beer = Beer(tap_id=beer['tapId'], beer_id=beer_id, volume=beer['volume'])
            beer = await beers.add(new_beer)
            self.write({'beer': beer})
            for tap in taps:  # Notify using WebSockets
                tap.write_message('Tap with id ' + str(beer['tapId']) + ' posted a new beer!')
        except UnValidVolumeError as error:
            logging.error(error.message)
            self.set_status(error.code)
            self.write(error.error)


class BeerHandler(tornado.web.RequestHandler):
    """
    HTTP handler for api/beers/:id endpoints:
    """

    async def get(self, beer_id=None):
        """
        Get Beer: GET method Handler that sends a specific beer as a response
        :param beer_id: The id of the beer to be returned
        :return: Returns the beer with the correspondent id if it exists. Otherwise returns a 404 error
        """
        try:
            beer = await beers.find_by_id(beer_id)
            self.write({'beer': beer})
        except NotFoundException as error:
            logging.error(error.message)
            self.set_status(error.code)
            self.write(error.error)

    async def delete(self, beer_id=None):
        """
        Delete Beer: DELETE method Handler that deletes a specific beer
        :param beer_id: The id of the beer to be deleted
        :return: None
        """
        try:
            await beers.delete(beer_id)
        except NotFoundException as error:
            logging.error(error.message)
            self.set_status(error.code)
            self.write(error.error)


class RealTimeHandler(tornado.websocket.WebSocketHandler):
    """
    Web Socket connections handler: Adds and removes connection to the active connections set.
    """

    def open(self) -> None:
        """
        When a new connection is opened, saves the connector in the taps set
        :return: None
        """
        taps.add(self)
        logging.info('A new tap has been connected to the system')

    def on_close(self) -> None:
        """
        When a connection closes, removes the connector from the taps set
        :return: None
        """
        taps.remove(self)
        logging.info('A tap has been disconnected from the system')


class Notifier(Observer):
    """
    Notifier: This class is attached to the BeerDB instance as an Observer and broadcasts a message upon DB operations
    """

    def on_notify(self, message) -> None:
        """
        We implement this method from the abstract Observer class so the BeersDB Observable can call it on DB updates
        :param message: Message from the BeersDB method that invoked the notification
        :return: None
        """
        logging.info('New DB Hook Notification: %s', message)
        for tap in taps:
            tap.write_message(message)


def make_app(port=8338):
    """
    Make App: Initializes a new Tornado App and sets request handlers
    :param port: The port the app should be listening to
    :return: App instance listening on the specified port
    """
    handlers = [
        (r"/api/beers", BeersHandler),
        (r"/api/beers/([^/]+)", BeerHandler),
        (r"/sockets/beers", RealTimeHandler),
    ]
    return tornado.web.Application(handlers).listen(port)


def ids(init):
    """
    Beer ID generator: Generates a new unique id each time it is called
    :param init: Value for the first generated id
    :return: A unique id
    """
    _id = init
    while True:
        yield _id
        _id += 1


if __name__ == "__main__":
    # Logger setup
    init_logger()
    # Create new BeerDB collection
    beers = BeerDB()
    logging.info('BeerDB Instance running')
    # Attach notifier
    notifier = Notifier()
    beers.attach(notifier)
    # Initialize beer_id generator
    beer_ids = ids(0)
    # Set of active connected taps
    taps = set()
    # Create and run web application
    port = int(os.environ['PORT'])
    app = make_app(port)
    logging.info('Started Web Service listening for connections on port %d', port)
    tornado.ioloop.IOLoop.current().start()
