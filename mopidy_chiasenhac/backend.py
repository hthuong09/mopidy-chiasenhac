import pykka
import logging
import requests
from mopidy import backend
from mopidy.models import Album, SearchResult, Track, Artist
from bs4 import BeautifulSoup
import re
import urllib

logger = logging.getLogger(__name__)

TRACK_URL = 'http://chiasenhac.vn/favourite/favourite~%s.html'
SEARCH_URL = 'http://search.chiasenhac.vn/search.php?s=%s'
uri_format = 'chiasenhac://%s____%s____%s____/%s'

_session = requests.Session()


def safe_uri(uri):
    uri = uri.encode('ascii', 'ignore')
    return uri


def chiasenhac_search(search_query):
    req = _session.get(SEARCH_URL % (search_query))
    soup = BeautifulSoup(req.text, 'html.parser')

    table = soup.find('table', class_='tbtable')
    rows = table.find_all('tr')

    tracks = []
    for row in rows:
        cols = row.find_all('td')
        if len(cols) == 0:
            continue
        song_artist_col = cols[1].find_all('p')
        url = song_artist_col[0].a['href']
        song_name = song_artist_col[0].a.string
        artist = song_artist_col[1].string
        int_length = parse_len(cols[2].span.contents[0])
        uri = uri_format % (url, artist, str(int_length), song_name)
        uri = safe_uri(uri)
        tracks.append(Track(
            name=song_name,
            length=int_length * 1000,
            album=Album(
                name='ChiaSeNhac',
            ),
            artists=[Artist(
                name=artist
            )],
            uri=uri
        ))

    if len(tracks) > 0:
        return tracks
    else:
        return None


def parse_len(length):
    minute = int(length.split(':')[0])
    second = int(length.split(':')[1])
    return minute * 60 + second


def parse_uri(uri):
    parts = uri.split('____')
    return {
        'uri': uri,
        'real_url': parts[0].replace('chiasenhac://', 'http://chiasenhac.vn/'),
        'artist': parts[1],
        'length': int(parts[2]),
        'name': parts[3]
    }


def resolve_track(uri):
    logger.debug("resolve_track: " + uri)
    uri_data = parse_uri(uri)
    track = Track(
        name=uri_data['name'],
        length=uri_data['length'] * 1000,
        album=Album(
            name='ChiaSeNhac',
        ),
        artists=[Artist(
            name=uri_data['artist']
        )],
        uri=uri
    )
    return [track]


class CSNBackend(pykka.ThreadingActor, backend.Backend):
    def __init__(self, config, audio):
        super(CSNBackend, self).__init__()
        if config['chiasenhac']['quality'] not in [128, 300, 500]:
            self.track_quality = 128
            logger.info('Invalid quality setting. Using default value: 128')
        else:
            self.track_quality = config['chiasenhac']

        self.library = CSNLibraryProvider(backend=self)
        self.playback = CSNPlaybackProvider(audio=audio, backend=self)
        self.uri_schemes = ['chiasenhac', 'csn']


class CSNLibraryProvider(backend.LibraryProvider):

    def lookup(self, track):
        return resolve_track(track)

    def search(self, query=None, uris=None, exact=False):
        if not query:
            return
        search_query = ' '.join(query.values()[0])
        logger.info("Searching ChiaSeNhac for query '%s'", search_query)
        tracks = chiasenhac_search(search_query)
        return SearchResult(
            uri="chiasenhac:search",
            tracks=tracks
        )


class CSNPlaybackProvider(backend.PlaybackProvider):
    def translate_uri(self, uri):
        logger.debug("translate_uri: " + uri)
        uri_data = parse_uri(uri)
        req = requests.get(uri_data['real_url'])
        m = re.search('decodeURIComponent\("([^"]+)"\)', req.text)
        return urllib.unquote(m.group(1))
