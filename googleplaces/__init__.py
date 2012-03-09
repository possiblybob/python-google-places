"""
A simple wrapper around the 'experimental' Google Places API, documented
here: http://code.google.com/apis/maps/documentation/places/. This library
also makes use of the v3 Maps API for geocoding.

Prerequisites: A Google API key with Places activated against it. Please
check the Google API console, here: http://code.google.com/apis/console

NOTE: Please ensure that you read the Google terms of service (labeled 'Limits
and Requirements' on the documentation url) prior to using this library in a
production environment.

@author: sam@slimkrazy.com
"""

try:
    import json
except ImportError:
    import simplejson as json
import urllib
import urllib2

import types


__all__ = ['GooglePlaces', 'GooglePlacesError', 'GooglePlacesAttributeError',
           'geocode_location']
__version__ = '0.8.0'
__author__ = 'Samuel Adu'
__email__ = 'sam@slimkrazy.com'

def _fetch_remote_json(service_url, params={}, use_http_post=False):
    """Retrieves a JSON object from a URL."""
    if not use_http_post:
        encoded_data = urllib.urlencode(params)
        query_url = (service_url if service_url.endswith('?') else
                     '%s?' % service_url)
        request_url = query_url + encoded_data
        request = urllib2.Request(request_url)
    else:
        request_url = service_url
        request = urllib2.Request(service_url, data=params)
    response = urllib2.urlopen(request)
    return (request_url, json.load(response))

def geocode_location(location, sensor=False):
    """Converts a human-readable location to lat-lng.

    Returns a dict with lat and lng keys.

    keyword arguments:
    location -- A human-readable location, e.g 'London, England'
    sensor   -- Boolean flag denoting if the location came from a device using
                its' location sensor (default False)

    raises:
    GooglePlacesError -- if the geocoder fails to find a location.
    """

    url, geo_response = _fetch_remote_json(
            GooglePlaces.GEOCODE_API_URL,
            {'address': location, 'sensor': str(sensor).lower()})
    _validate_response(url, geo_response)
    if geo_response['status'] == GooglePlaces.RESPONSE_STATUS_ZERO_RESULTS:
        error_detail = ('Lat/Lng for location \'%s\' can\'t be determined.' %
                        location)
        raise GooglePlacesError, error_detail
    return geo_response['results'][0]['geometry']['location']

def _get_place_details(reference, api_key, sensor=False):
    """Gets a detailed place response.

    keyword arguments:
    reference -- The unique Google reference for the required place.
    """
    url, detail_response = _fetch_remote_json(GooglePlaces.DETAIL_API_URL,
                                              {'reference': reference,
                                               'sensor': str(sensor).lower(),
                                               'key': api_key})
    _validate_response(url, detail_response)
    return detail_response['result']

def _validate_response(url, response):
    """Validates that the response from Google was successful."""
    if response['status'] not in [GooglePlaces.RESPONSE_STATUS_OK,
                                  GooglePlaces.RESPONSE_STATUS_ZERO_RESULTS]:
        error_detail = ('Request to URL %s failed with response code: %s' %
                        (url, response['status']))
        raise GooglePlacesError, error_detail


class GooglePlacesError(Exception):
    pass


class GooglePlacesAttributeError(AttributeError):
    """Exception thrown when a detailed property is unavailable.

    A search query from the places API returns only a summary of the Place.
    in order to get full details, a further API call must be made using
    the place reference. This exception will be thrown when a property made
    available by only the detailed API call is looked up against the summary
    object.

    An explicit call to get_details() must be made on the summary object in
    order to convert a summary object to a detailed object.
    """
    # I could spend forever muling between this design decision and creating
    # a PlaceSummary object as well as a Place object. I'm leaning towards this
    # method in order to keep the API as simple as possible.
    pass


class GooglePlaces(object):
    """A wrapper around the Google Places Query API."""

    GEOCODE_API_URL = 'https://maps.googleapis.com/maps/api/geocode/json?'
    QUERY_API_URL = 'https://maps.googleapis.com/maps/api/place/search/json?'
    DETAIL_API_URL = ('https://maps.googleapis.com/maps/api/place/details/' +
                      'json?')
    CHECKIN_API_URL = ('https://maps.googleapis.com/maps/api/place/check-in/' +
                       'json?sensor=%s&key=%s')
    MAXIMUM_SEARCH_RADIUS = 50000
    RESPONSE_STATUS_OK = 'OK'
    RESPONSE_STATUS_ZERO_RESULTS = 'ZERO_RESULTS'

    def __init__(self, api_key):
        self._api_key = api_key
        self._sensor = False
        self._request_params = None

    def query(self, location=None, lat_lng=None, keyword=None, radius=3200,
              sensor=False, types=[], name=None):
        """Perform a search using the Google Places API.

        One of either location or lat_lng are required, the rest of the keyword
        arguments are optional.

        keyword arguments:
        location -- A human readable location, e.g 'London, England'
                    (default None)
        lat_lng  -- A dict containing the following keys: lat, lng
                    (default None)
        keyword  -- A term to be matched against all available fields, including
                    but not limited to name, type, and address (default None)
        radius   -- The radius (in meters) around the location/lat_lng to
                    restrict the search to. The maximum is 50000 meters.
                    (default 3200)
        sensor   -- Indicates whether or not the Place request came from a
                    device using a location sensor (default False)
        types    -- An optional list of types, restricting the results to
                    Places (default [])
        name     -- A term to be matched against against the names of Places.
                    Results will be restricted to those containing this value.
                    (default None)
        """
        if location is None and lat_lng is None:
            raise ValueError('One of location or lat_lng must be passed in.')
        self._sensor = sensor
        self._lat_lng = (lat_lng if lat_lng is not None
                         else geocode_location(location))
        radius = (radius if radius <= GooglePlaces.MAXIMUM_SEARCH_RADIUS
                  else GooglePlaces.MAXIMUM_SEARCH_RADIUS)
        lat_lng_str = '%(lat)s,%(lng)s' % self._lat_lng
        self._request_params = {'location': lat_lng_str, 'radius': radius}
        if len(types) > 0:
            self._request_params['types'] = '|'.join(types)
        if keyword is not None:
            self._request_params['keyword'] = keyword
        if name is not None:
            self._request_params['name'] = name
        self._add_required_param_keys()
        url, places_response = _fetch_remote_json(
                GooglePlaces.QUERY_API_URL, self._request_params)
        _validate_response(url, places_response)
        return GooglePlacesSearchResult(self, places_response)

    def checkin(self, reference, sensor=False):
        """Checks in a user to a place.

        keyword arguments:
        reference -- The unique Google reference for the relevant place.
        sensor    -- Boolean flag denoting if the location came from a
                         device using its' location sensor (default False)
        """
        data = {'reference': reference}
        url, checkin_response = _fetch_remote_json(
                GooglePlaces.CHECKIN_API_URL % (str(sensor).lower(),
                        self.api_key), json.dumps(data), use_http_post=True)
        _validate_response(url, checkin_response)

    def get_place(self, reference, sensor=False):
        """Gets a detailed place object.

        keyword arguments:
        reference -- The unique Google reference for the required place.
        sensor    -- Boolean flag denoting if the location came from a
                         device using its' location sensor (default False)
        """
        place_details = _get_place_details(reference, self.api_key, sensor)
        return Place(self, place_details)

    def _add_required_param_keys(self):
        self._request_params['key'] = self.api_key
        self._request_params['sensor'] = str(self.sensor).lower()

    @property
    def request_params(self):
        return self._request_params

    @property
    def api_key(self):
        return self._api_key

    @property
    def sensor(self):
        return self._sensor


class GooglePlacesSearchResult(object):
    """Wrapper around the Google Places API query JSON response."""

    def __init__(self, query_instance, response):
        self._places = []
        for place in response['results']:
            self._places.append(Place(query_instance, place))
        self._html_attributions = response['html_attributions']

    @property
    def places(self):
        return self._places

    @property
    def html_attributions(self):
        """Returns the HTML attributions for the specified response.

        Any returned HTML attributions MUST be displayed as-is, in accordance
        with the requirements as found in the documentation. Please see the
        module comments for links to the relevant url.
        """
        return self._html_attributions

    @property
    def has_attributions(self):
        """Returns a flag denoting if the response had any html attributions."""
        return len(self.html_attributions) > 0


class Place(object):
    """
    Represents a place from the results of a Google Places API query.
    """
    def __init__(self, query_instance, place_data):
        self._query_instance = query_instance
        self._id = place_data['id']
        self._reference = place_data['reference']
        self._name = place_data['name']
        self._vicinity = place_data['vicinity']
        self._geo_location = place_data['geometry']['location']
        self._rating = place_data.get('rating')
        self._types = place_data.get('types')
        self._icon = place_data.get('icon')
        if place_data.get('address_components') is None:
            self._details = None
        else:
            self._details = place_data

    @property
    def reference(self):
        """Returns contains a unique token for the place.

        The token can be used to retrieve additional information about this
        place when invoking the getPlace method on an GooglePlaces instance.

        You can store this token and use it at any time in future to refresh
        cached data about this Place, but the same token is not guaranteed to
        be returned for any given Place across different searches."""
        return self._reference

    @property
    def id(self):
        """Returns the unique stable identifier denoting this place.

        This identifier may not be used to retrieve information about this
        place, but is guaranteed to be valid across sessions. It can be used
        to consolidate data about this Place, and to verify the identity of a
        Place across separate searches.
        """
        return self._id

    @property
    def icon(self):
        """Returns the URL of a recommended icon for display."""
        return self._icon

    @property
    def types(self):
        """Returns a list of feature types describing the given result."""
        return self._types

    @property
    def geo_location(self):
        """Returns the lat lng co-ordinates of the place.

        A dict with the keys 'lat' and 'lng' will be returned.
        """
        return self._geo_location

    @property
    def name(self):
        """Returns the human-readable name of the place."""
        return self._name

    @property
    def vicinity(self):
        """Returns a feature name of a nearby location.

        Often this feature refers to a street or neighborhood within the given
        results.
        """
        return self._vicinity

    @property
    def rating(self):
        """Returns the Place's rating, from 0.0 to 5.0, based on user reviews.

        This method will return None for places that have no rating.
        """
        return self._rating

    # The following properties require a further API call in order to be
    # available.
    @property
    def details(self):
        """Returns the JSON response from Google Places Detail search API."""
        self._validate_status()
        return self._details

    @property
    def formatted_address(self):
        """Returns a string containing the human-readable address of this place.

        Often this address is equivalent to the "postal address," which
        sometimes differs from country to country. (Note that some countries,
        such as the United Kingdom, do not allow distribution of complete postal
        addresses due to licensing restrictions.)
        """
        self._validate_status()
        return self.details.get('formatted_address')

    @property
    def local_phone_number(self):
        """Returns the Place's phone number in its local format."""
        self._validate_status()
        return self.details.get('formatted_phone_number')

    @property
    def international_phone_number(self):
        self._validate_status()
        return self.details.get('international_phone_number')

    @property
    def website(self):
        """Retuns the authoritative website for this Place."""
        self._validate_status()
        return self.details.get('website')

    @property
    def url(self):
        """Contains the official Google Place Page URL of this establishment.

        Applications must link to or embed the Google Place page on any screen
        that shows detailed results about this Place to the user.
        """
        self._validate_status()
        return self.details.get('url')

    @property
    def html_attributions(self):
        """Returns the HTML attributions for the specified response.

        Any returned HTML attributions MUST be displayed as-is, in accordance
        with the requirements as found in the documentation. Please see the
        module comments for links to the relevant url.
        """
        self._validate_status()
        return self.details.get('html_attributions', [])

    @property
    def has_attributions(self):
        """Returns a flag denoting if the response had any html attributions."""
        return (False if self._details is None else
                len(self.html_attributions) > 0)

    def checkin(self):
        """Checks in an anonynomous user in."""
        self._query_instance.checkin(self.reference,
                                     self._query_instance.sensor)

    def get_details(self):
        """Retrieves full information on the place matching the reference.

        Further attributes will be made available on the instance once this
        method has been invoked.
        """
        if self._details is None:
            self._details = _get_place_details(
                    self.reference, self._query_instance.api_key,
                    self._query_instance.sensor)

    def _validate_status(self):
        if self._details is None:
            error_detail = ('The attribute requested is only available after ' +
                    'an explicit call to get_details() is made.')
            raise GooglePlacesAttributeError, error_detail
