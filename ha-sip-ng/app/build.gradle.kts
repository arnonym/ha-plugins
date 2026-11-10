import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.kotlin.jvm)
    application
    alias(libs.plugins.shadow)
    alias(libs.plugins.ktlint)
}

repositories {
    mavenCentral()
}

val pjsua2JarFile = layout.projectDirectory.file("libs/pjsua2.jar").asFile
val pjsua2Jar = if (pjsua2JarFile.exists()) files(pjsua2JarFile) else files()

dependencies {
    // Everything except the pjsip bindings themselves lives in :core (HTTP/MQTT
    // clients, config, menu/command logic, logging) -- see core/build.gradle.kts.
    implementation(project(":core"))

    // The generated org.pjsip.pjsua2 Java SWIG bindings (classes + JNI stub) are
    // built from pjproject 2.17 source in Docker (see the `pjsip-bindings` stage
    // in ../Dockerfile, validated in the Phase 0 spike) since no such artifact is
    // published to any Maven repository. Run `./gradlew :app:extractPjsua2Bindings`
    // once (requires docker or podman) to populate app/libs/pjsua2.jar for local
    // (non-Docker) compilation/tests/runs. Until then, `pjsua2Jar` below resolves
    // to an empty file collection so the rest of the module still builds (just
    // without the actual SIP layer functioning). Included via `implementation`
    // (not `compileOnly`) so it's on the runtime classpath and bundled into the
    // shadow jar -- the separate libpjsua2.so JNI native lib is loaded
    // independently via `-Djava.library.path`/`System.loadLibrary`.
    implementation(pjsua2Jar)

    testImplementation(pjsua2Jar)
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

application {
    mainClass.set("io.github.arnonym.MainKt")
}

tasks.test {
    useJUnitPlatform()
}

tasks.shadowJar {
    archiveBaseName.set("ha-sip")
    archiveClassifier.set("")
    archiveVersion.set("")
    // JEP 472: loading native code (pjsip's libpjsua2 via System.loadLibrary, and JNA,
    // which Clikt's terminal library pulls in) needs explicit permission since JDK 24 --
    // a warning for now, blocked in a future release. This manifest attribute grants it
    // to everything launched as `java -jar ha-sip.jar`, with no extra command-line flag.
    manifest {
        attributes("Enable-Native-Access" to "ALL-UNNAMED")
    }
    // Shadow 9 excludes duplicate paths by default, which would hand only the first
    // copy of each META-INF/services file to the merging transformer -- dropping e.g.
    // ktor's engine or slf4j's provider registrations. Let duplicates through to the
    // transformers, and exclude them everywhere else as before.
    duplicatesStrategy = DuplicatesStrategy.INCLUDE
    mergeServiceFiles()
    filesNotMatching(listOf("META-INF/services/**", "META-INF/*.kotlin_module")) {
        duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    }
}

// Builds the `pjsip-bindings` stage of ../Dockerfile and extracts org.pjsip.pjsua2
// (as libs/pjsua2.jar) + the JNI native lib (as native/<arch>/libpjsua2.so) so this
// module can be compiled/tested/run locally without Docker on every build.
// Requires podman or docker. Re-run manually whenever the pjproject version pinned
// in ../Dockerfile changes.
tasks.register<Exec>("extractPjsua2Bindings") {
    group = "pjsip"
    description = "Builds the PJSIP Java SWIG bindings in a container and extracts them into libs/ and native/"
    commandLine("${rootProject.projectDir}/../scripts/extract-pjsua2-bindings.sh")
}
