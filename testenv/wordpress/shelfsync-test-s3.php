<?php
/**
 * Plugin Name: ShelfSync test stack: S3 test server
 * Description: Points the Amazon S3 Storage extension at the ShelfSync test stack's S3 server (testenv/moto_s3.py, 127.0.0.1:47630). For the local test site only.
 *
 * Copied by the owner into the test site's wp-content\mu-plugins folder (runbooks/test-stack.md §3.4).
 * Pattern from Kestrel's "use alternative cloud storage platforms" snippet
 * (kestrelwp.com/docs/s3-compatible-providers/): set the provider to
 * "User defined (experimental)" in WooCommerce > S3 storage first, or these filters do nothing.
 * The keys below are made up: the S3 test server checks none. Never put real AWS keys here.
 */

defined( 'ABSPATH' ) || exit;

/** Acts only on the ShelfSync test site, never on another site this file is copied to. */
function shelfsync_test_s3_is_test_site() {
	return 'shelfsync-test.test' === wp_parse_url( home_url(), PHP_URL_HOST );
}

// Kestrel documents backblaze, digitalocean and wasabi; none is the test server, and
// digitalocean is the one whose region stays us-east-1, like the test server's (04-A V6, to verify).
add_filter(
	'woocommerce_amazon_s3_client_cloud_service',
	function ( $service ) {
		return shelfsync_test_s3_is_test_site() ? 'digitalocean' : $service;
	}
);

add_filter(
	'woocommerce_amazon_s3_client_args',
	function ( $args ) {
		if ( ! shelfsync_test_s3_is_test_site() ) {
			return $args;
		}
		$args['region']      = 'us-east-1';
		$args['endpoint']    = 'http://127.0.0.1:47630';
		// The test server answers only Host 127.0.0.1:<port>, so the bucket goes in the path,
		// not in the host name (AWS SDK for PHP's S3 client option; 04-A V6, to verify).
		$args['use_path_style_endpoint'] = true;
		$args['credentials'] = array(
			'key'    => 'TESTSTACKREADWRITE',
			'secret' => 'TestStackSecretReadWrite1',
		);
		return $args;
	}
);
