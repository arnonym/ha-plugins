import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ktlint)
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(libs.clikt)
    implementation(libs.kotlinx.coroutines.core)
    // `api` (not `implementation`): JsonObject/JsonElement appear directly in the
    // public signatures of Menu/Command/Webhook/etc. -- :app needs these types too.
    api(libs.kotlinx.serialization.json)
    implementation(libs.snakeyaml)
    implementation(libs.dotenv.java)

    // :core deliberately holds *every* non-pjsip dependency (HTTP client, MQTT
    // client, logging) -- :app only adds the pjsip SWIG bindings + application/
    // shadow plugin wiring on top of :core. This keeps the pjsip-free surface as
    // large and as host-testable as possible.
    implementation(libs.ktor.client.core)
    implementation(libs.ktor.client.cio)
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.serialization.kotlinx.json)
    implementation(libs.ktor.client.websockets)
    implementation(libs.ktor.client.logging)

    implementation(libs.hivemq.mqtt.client)

    implementation(libs.slf4j.api)
    runtimeOnly(libs.logback.classic)

    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
    testImplementation(libs.kotest.assertions.core)
}

// Targets Java 25 bytecode (matching the JRE installed in the production image)
// without requiring a JDK 25 *toolchain* to be locally installed -- any JDK 25+
// can compile down to an older bytecode target via -jvm-target.
kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_25)
    }
}

java {
    sourceCompatibility = JavaVersion.VERSION_25
    targetCompatibility = JavaVersion.VERSION_25
}

ktlint {
    version.set(libs.versions.ktlint.engine)
}

tasks.test {
    useJUnitPlatform()
}
