"""
Tests for IslandConnectivityDistributionModel.

The model is a wrapper around the residual-demand traffic model: an off-island trip is
accessible only if (a) at least one mainland connector (bridge/tunnel) is functional AND
(b) the traffic model finds a working on-island path from THAT connector's nearest node to
the business. Both legs must hold on the *same* connector.

Coverage:
  * constructor: which components become connectors / off-island ids
  * is_connected / is_outside_island
  * is_building_accessible dispatch (abstain / both-off-island / one-off-island)
  * is_reachable_from_mainland - the core, including the "a connector is always up but the
    road to it is severed" case the model must reject
  * business_has_off_island_link
  * integration with a REAL ResidualDemand traffic model (connector->node mapping, OD-trip
    registration, real path scoring) and the system-creator wiring second pass
"""
import shutil
import pytest
import pandas as pd
from pyrecodes import main
from pyrecodes.utilities import read_json_file
from pyrecodes.business.business import Business
from pyrecodes.component.r2d_component import R2DBridge, R2DTunnel, R2DBuilding, R2DBuildingWithBusiness
from pyrecodes.resource_distribution_model.residual_demand_traffic_distribution_model import ResidualDemandTrafficDistributionModel
from pyrecodes.resource_distribution_model.island_connectivity_distribution_model import IslandConnectivityDistributionModel
from tests.test_resource_distribution_model.test_resource_distribution_model_inputs import (
    MAIN_FILE_RESIDUAL_DEMAND, RESOURCE_NAME_RESIDUAL_DEMAND, RESOURCE_PARAMETERS_RESIDUAL_DEMAND)

RESOURCE_NAME = 'IslandConnectivity'


# --------------------------------------------------------------------------- helpers

def make_connector(aim_id, latitude=0.0, longitude=0.0, functionality_level=1.0,
                   cls=R2DBridge, mainland_connector=True):
    connector = cls()
    connector.aim_id = aim_id
    connector.functionality_level = functionality_level
    connector.general_information = {'location': {'latitude': latitude, 'longitude': longitude}}
    if mainland_connector:
        connector.general_information['MainlandConnector'] = True
    return connector


def make_building(aim_id, outside_island=False):
    building = R2DBuilding()
    building.aim_id = aim_id
    if outside_island:
        building.general_information['OutsideIsland'] = True
    return building


def make_business_building(aim_id, business_parameters_list=()):
    component = R2DBuildingWithBusiness()
    component.aim_id = aim_id
    component.businesses = [Business(str(i + 1), params, component)
                           for i, params in enumerate(business_parameters_list)]
    return component


def business_params(employee=(), suppliers=(), outside_customers=(), visitor_cbgs=None):
    return {
        'SalesVolume': 1000,
        'EmployeeLocations': list(employee),
        'NearestRetailLocations': list(suppliers),
        'OutsideIslandCustomerBuildings': list(outside_customers),
        'VisitorHomeCBGs': dict(visitor_cbgs or {}),
    }


def make_island(components, params=None):
    return IslandConnectivityDistributionModel(RESOURCE_NAME, params or {}, list(components))


class FakeTrafficModel:
    """Stand-in for ResidualDemand: deterministic node lookup and path scoring."""
    def __init__(self, node_dict=None, accessible_pairs=()):
        self.building_to_traffic_node_dict = dict(node_dict or {})
        self._accessible = set(accessible_pairs)

    def path_accessible(self, time_step, origin_node, destination_node):
        return (origin_node, destination_node) in self._accessible


def make_travel_setup(traffic_model, od_pairs):
    """Configure a real ResidualDemand model's precomputed travel times for is-accessible
    checks. od_pairs: list of (origin_nid, destin_nid, travel_time, change_factor)."""
    records = [{'agent_id': float(i + 1), 'origin_nid': o, 'destin_nid': d, 'travel_time_used': t}
               for i, (o, d, t, _) in enumerate(od_pairs)]
    traffic_model.travel_times = [pd.DataFrame(records)]
    # trip_index is a list parallel to travel_times (one (origin,destin)->row dict per step).
    traffic_model.trip_index = [{(r['origin_nid'], r['destin_nid']): i for i, r in enumerate(records)}]
    traffic_model.travel_time_change_index = [{float(i + 1): cf for i, (_, _, _, cf) in enumerate(od_pairs)}]
    traffic_model.travel_time_change_factors = [
        [{'agent_id': float(i + 1), 'travel_time_change': cf} for i, (_, _, _, cf) in enumerate(od_pairs)]]
    traffic_model.od_trip_checker.isolated_nodes = set()


# --------------------------------------------------------------------------- construction

class TestConstruction:

    def test_finds_mainland_connectors(self):
        bridge = make_connector('B1')
        tunnel = make_connector('T1', cls=R2DTunnel)
        non_connector_bridge = make_connector('B2', mainland_connector=False)
        building = make_building('10')
        island = make_island([bridge, tunnel, non_connector_bridge, building])
        assert set(island.mainland_connectors) == {bridge, tunnel}

    def test_finds_outside_island_building_ids(self):
        off1 = make_building('off1', outside_island=True)
        off2 = make_building('off2', outside_island=True)
        on = make_building('on1', outside_island=False)
        island = make_island([off1, off2, on])
        assert island.outside_island_building_ids == {'off1', 'off2'}

    def test_init_defaults_before_wiring(self):
        island = make_island([make_connector('B1')])
        assert island.traffic_model is None
        assert island.connector_nodes == {}

    def test_no_connectors_no_off_island(self):
        island = make_island([make_building('on1')])
        assert island.mainland_connectors == []
        assert island.outside_island_building_ids == set()


# --------------------------------------------------------------------------- is_connected

class TestIsConnected:

    def test_true_when_any_connector_functional(self):
        island = make_island([make_connector('B1', functionality_level=0.0),
                              make_connector('B2', functionality_level=0.3)])
        assert island.is_connected() is True

    def test_false_when_all_connectors_zero(self):
        island = make_island([make_connector('B1', functionality_level=0.0),
                              make_connector('B2', functionality_level=0.0)])
        assert island.is_connected() is False

    def test_false_when_no_connectors(self):
        assert make_island([make_building('on1')]).is_connected() is False

    def test_outside_island_lookup(self):
        island = make_island([make_building('off1', outside_island=True), make_building('on1')])
        assert island.is_outside_island('off1') is True
        assert island.is_outside_island('on1') is False
        assert island.is_outside_island('unknown') is False


# ----------------------------------------------------------------- is_building_accessible

class TestIsBuildingAccessibleDispatch:

    def _island_with_fake(self, reachable):
        island = make_island([make_connector('B1'),
                              make_building('off', outside_island=True),
                              make_building('on')])
        island.traffic_model = FakeTrafficModel(
            node_dict={'on': 2},
            accessible_pairs=[(1, 2)] if reachable else [])
        island.connector_nodes = {island.mainland_connectors[0]: 1}
        return island

    def test_abstains_when_neither_off_island(self):
        island = self._island_with_fake(reachable=True)
        assert island.is_building_accessible(0, 'on', 'on') is None

    def test_both_off_island_returns_is_connected(self):
        island = make_island([make_connector('B1', functionality_level=1.0),
                              make_building('a', outside_island=True),
                              make_building('b', outside_island=True)])
        assert island.is_building_accessible(0, 'a', 'b') is True
        island.mainland_connectors[0].functionality_level = 0.0
        assert island.is_building_accessible(0, 'a', 'b') is False

    def test_one_off_island_origin_delegates_to_business(self):
        island = self._island_with_fake(reachable=True)
        # origin off-island -> route to the on-island destination ('on')
        assert island.is_building_accessible(0, 'off', 'on') is True

    def test_one_off_island_destination_delegates_to_business(self):
        island = self._island_with_fake(reachable=True)
        # destination off-island -> route to the on-island origin ('on')
        assert island.is_building_accessible(0, 'on', 'off') is True

    def test_one_off_island_not_reachable(self):
        island = self._island_with_fake(reachable=False)
        assert island.is_building_accessible(0, 'off', 'on') is False


# -------------------------------------------------------------- is_reachable_from_mainland

class TestIsReachableFromMainland:
    """The heart of the model. Builds an island with two connectors and a fake traffic
    model so connector functionality and per-connector path accessibility are controlled
    independently."""

    def _build(self, funcA=1.0, funcB=1.0, accessible_pairs=()):
        connA = make_connector('A', functionality_level=funcA)
        connB = make_connector('B', functionality_level=funcB)
        island = make_island([connA, connB])
        island.traffic_model = FakeTrafficModel(node_dict={'biz': 99}, accessible_pairs=accessible_pairs)
        island.connector_nodes = {connA: 10, connB: 20}
        return island, connA, connB

    def test_no_traffic_model_falls_back_to_is_connected(self):
        island = make_island([make_connector('A', functionality_level=0.5)])
        assert island.traffic_model is None
        assert island.is_reachable_from_mainland(0, 'biz') is True
        island.mainland_connectors[0].functionality_level = 0.0
        assert island.is_reachable_from_mainland(0, 'biz') is False

    def test_business_not_on_graph_falls_back_to_is_connected(self):
        island, connA, connB = self._build(funcA=1.0, funcB=0.0, accessible_pairs=[(10, 99)])
        # 'unmapped' is not in building_to_traffic_node_dict -> fall back to is_connected (A up)
        assert island.is_reachable_from_mainland(0, 'unmapped') is True
        connA.functionality_level = 0.0
        assert island.is_reachable_from_mainland(0, 'unmapped') is False

    def test_true_when_functional_connector_has_path(self):
        island, _, _ = self._build(funcA=1.0, funcB=1.0, accessible_pairs=[(10, 99)])
        assert island.is_reachable_from_mainland(0, 'biz') is True

    def test_not_reachable_when_connector_up_but_path_severed(self):
        # The exact concern: a connector is functional, but no road path reaches the business.
        island, _, _ = self._build(funcA=1.0, funcB=1.0, accessible_pairs=[])
        assert island.is_reachable_from_mainland(0, 'biz') is False

    def test_not_reachable_when_path_exists_but_connector_down(self):
        # Path from connector A's node is fine, but A is collapsed -> not reachable.
        island, _, _ = self._build(funcA=0.0, funcB=0.0, accessible_pairs=[(10, 99)])
        assert island.is_reachable_from_mainland(0, 'biz') is False

    def test_requires_functional_and_path_on_same_connector(self):
        # A is up but its path is severed; B has a clear path but is collapsed. Neither single
        # connector satisfies BOTH conditions -> not reachable, even though one connector is up
        # and one path exists.
        island, connA, connB = self._build(funcA=1.0, funcB=0.0, accessible_pairs=[(20, 99)])
        assert island.is_reachable_from_mainland(0, 'biz') is False
        # Now give A a clear path too -> reachable.
        island.traffic_model._accessible.add((10, 99))
        assert island.is_reachable_from_mainland(0, 'biz') is True

    def test_any_single_good_connector_suffices(self):
        # A down, B up with a clear path -> reachable.
        island, _, _ = self._build(funcA=0.0, funcB=1.0, accessible_pairs=[(20, 99)])
        assert island.is_reachable_from_mainland(0, 'biz') is True


# ---------------------------------------------------------------- business off-island links

class TestBusinessHasOffIslandLink:

    def _island(self):
        # 'OFF' is off-island; on-island ids are not flagged.
        return make_island([make_building('OFF', outside_island=True), make_building('ON')])

    def test_off_island_employee(self):
        island = self._island()
        biz = Business('1', business_params(employee=['OFF']), make_building('home'))
        assert island.business_has_off_island_link(biz) is True

    def test_off_island_supplier(self):
        island = self._island()
        biz = Business('1', business_params(suppliers=['OFF']), make_building('home'))
        assert island.business_has_off_island_link(biz) is True

    def test_off_island_customer_building(self):
        island = self._island()
        biz = Business('1', business_params(outside_customers=['OFF']), make_building('home'))
        assert island.business_has_off_island_link(biz) is True

    def test_others_customer_block(self):
        island = self._island()
        biz = Business('1', business_params(visitor_cbgs={'060014272001': 0.8, 'Others': 0.2}),
                       make_building('home'))
        assert island.business_has_off_island_link(biz) is True

    def test_no_off_island_link(self):
        island = self._island()
        biz = Business('1', business_params(employee=['ON'], suppliers=['ON'],
                                            visitor_cbgs={'060014272001': 1.0}),
                       make_building('home'))
        assert island.business_has_off_island_link(biz) is False


# ----------------------------------------------------------------- trivial distribute API

class TestDistributeApi:
    def test_distribute_is_noop_and_totals_zero(self):
        island = make_island([make_connector('A')])
        assert island.distribute(0) is None
        assert island.get_total_supply() == 0
        assert island.get_total_demand() == 0
        assert island.get_total_consumption() == 0


# ----------------------------------------------------- integration with a real traffic model

class TestIntegrationWithRealTrafficModel:
    """Uses the real ThreeLocalities ResidualDemand model: 3 nodes at
    (lon,lat) = (0,0)=node0, (0.1,0.1)=node1, (0,0.2)=node2, OD pairs (0,2),(2,0),(1,2),(2,1)."""

    @pytest.fixture
    def residual_demand(self):
        system = main.create_system(read_json_file(MAIN_FILE_RESIDUAL_DEMAND))
        model = ResidualDemandTrafficDistributionModel(
            RESOURCE_NAME_RESIDUAL_DEMAND, RESOURCE_PARAMETERS_RESIDUAL_DEMAND, system.components)
        model.distribution_time_steps = [0]
        return model

    def test_find_connector_nodes_maps_to_nearest(self, residual_demand):
        near1 = make_connector('B1', latitude=0.1, longitude=0.1)
        near0 = make_connector('B0', latitude=0.0, longitude=0.0)
        near2 = make_connector('B2', latitude=0.2, longitude=0.0)
        island = make_island([near1, near0, near2])
        nodes = island.find_connector_nodes(residual_demand)
        assert nodes[near1] == 1
        assert nodes[near0] == 0
        assert nodes[near2] == 2

    def test_register_connector_trips_adds_pair(self, residual_demand, tmp_path):
        original = residual_demand.od_trip_checker.od_matrix_filename
        temp = str(tmp_path / 'OD_Matrix_test.csv')
        shutil.copy(original, temp)
        residual_demand.od_trip_checker.od_matrix_filename = temp

        biz_building = make_business_building('biz', [business_params(employee=['OFF'])])
        off = make_building('OFF', outside_island=True)
        connector = make_connector('B1', latitude=0.1, longitude=0.1)   # -> node 1
        residual_demand.building_to_traffic_node_dict['biz'] = 0         # (1,0) is NOT in the OD matrix

        island = make_island([connector, off, biz_building])
        before = len(residual_demand.od_trip_checker.od_matrix)
        island.set_transfer_service_distribution_model(residual_demand)
        after = len(residual_demand.od_trip_checker.od_matrix)

        assert island.traffic_model is residual_demand
        assert island.connector_nodes[connector] == 1
        assert after == before + 1
        assert residual_demand.od_trip_checker.check_trip_in_od_matrix(1, 0)

    def test_register_skips_businesses_without_off_island_link(self, residual_demand, tmp_path):
        original = residual_demand.od_trip_checker.od_matrix_filename
        temp = str(tmp_path / 'OD_Matrix_test.csv')
        shutil.copy(original, temp)
        residual_demand.od_trip_checker.od_matrix_filename = temp

        biz_building = make_business_building('biz', [business_params(employee=['ON'])])  # no off-island link
        connector = make_connector('B1', latitude=0.1, longitude=0.1)
        residual_demand.building_to_traffic_node_dict['biz'] = 0
        island = make_island([connector, biz_building])

        before = len(residual_demand.od_trip_checker.od_matrix)
        island.set_transfer_service_distribution_model(residual_demand)
        assert len(residual_demand.od_trip_checker.od_matrix) == before

    def test_reachable_with_real_path_accessible(self, residual_demand):
        connector = make_connector('B1', latitude=0.1, longitude=0.1)   # -> node 1
        island = make_island([connector])
        island.traffic_model = residual_demand
        island.connector_nodes = island.find_connector_nodes(residual_demand)
        residual_demand.building_to_traffic_node_dict['biz'] = 2

        # functional connector + accessible path -> reachable
        make_travel_setup(residual_demand, [(1, 2, 1000.0, 1.0)])
        assert island.is_reachable_from_mainland(0, 'biz') is True

        # functional connector but path severed (travel time / change factor exceed cutoffs)
        make_travel_setup(residual_demand, [(1, 2, 20000.0, 5.0)])
        assert island.is_reachable_from_mainland(0, 'biz') is False

        # clear path but connector collapsed -> not reachable
        make_travel_setup(residual_demand, [(1, 2, 1000.0, 1.0)])
        connector.functionality_level = 0.0
        assert island.is_reachable_from_mainland(0, 'biz') is False

    def test_end_to_end_real_routing(self, residual_demand):
        # Drive the real traffic simulator: connector at node 1, business at node 2; the OD
        # matrix contains the (1,2) trip, which is routable in the undamaged network.
        connector = make_connector('B1', latitude=0.1, longitude=0.1)
        island = make_island([connector])
        island.traffic_model = residual_demand
        island.connector_nodes = island.find_connector_nodes(residual_demand)
        residual_demand.building_to_traffic_node_dict['biz'] = 2

        residual_demand.distribute_traffic(0)   # real routing, builds trip_index + change factors
        assert island.is_reachable_from_mainland(0, 'biz') is True

        # Collapsing the only connector cuts the business off regardless of the road path.
        connector.functionality_level = 0.0
        assert island.is_reachable_from_mainland(0, 'biz') is False


# --------------------------------------------------------- system-creator wiring second pass

class TestTransferServiceWiringSecondPass:
    """Verifies the get_transfer_services second pass injects one transfer service into
    another when the latter declares a TransferService dependency (IslandConnectivity ->
    TransportationService)."""

    def test_dependent_transfer_service_gets_wired(self, monkeypatch):
        from pyrecodes.system_creator.concrete_system_creator import ConcreteSystemCreator

        class Stub:
            def __init__(self, name):
                self.name = name
                self.received = []

            def set_transfer_service_distribution_model(self, other):
                self.received.append(other)

        stubs = {'TransportationService': Stub('TransportationService'),
                 'IslandConnectivity': Stub('IslandConnectivity')}

        creator = ConcreteSystemCreator()
        monkeypatch.setattr(creator, 'get_resource_distribution_model',
                            lambda name, params, components: stubs[name])

        all_params = {
            'TransportationService': {'Group': 'TransferService',
                                      'DistributionModel': {'Parameters': {}}},
            'IslandConnectivity': {'Group': 'TransferService',
                                   'DistributionModel': {'Parameters': {'TransferService': 'TransportationService'}}},
        }
        creator.get_transfer_services([], all_params)

        assert stubs['IslandConnectivity'].received == [stubs['TransportationService']]
        assert stubs['TransportationService'].received == []

    def test_list_valued_transfer_service_dependency(self, monkeypatch):
        from pyrecodes.system_creator.concrete_system_creator import ConcreteSystemCreator

        class Stub:
            def __init__(self):
                self.received = []

            def set_transfer_service_distribution_model(self, other):
                self.received.append(other)

        stubs = {'A': Stub(), 'B': Stub(), 'C': Stub()}
        creator = ConcreteSystemCreator()
        monkeypatch.setattr(creator, 'get_resource_distribution_model',
                            lambda name, params, components: stubs[name])
        all_params = {
            'A': {'Group': 'TransferService', 'DistributionModel': {'Parameters': {}}},
            'B': {'Group': 'TransferService', 'DistributionModel': {'Parameters': {}}},
            'C': {'Group': 'TransferService', 'DistributionModel': {'Parameters': {'TransferService': ['A', 'B']}}},
        }
        creator.get_transfer_services([], all_params)
        assert stubs['C'].received == [stubs['A'], stubs['B']]
